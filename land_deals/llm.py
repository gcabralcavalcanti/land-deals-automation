"""Wrapper around the Claude API.

- JSON answers constrained by a JSON Schema (structured outputs) and validated again locally.
- Every answer is recorded under recordings/<task>-<hash>.json. The same request is never paid twice,
  and without an API key the recordings replay the run (demo mode).
- Call cap per run, timeout, SDK retries, one schema retry, a JSON log line per call with tokens and cost.
- The key comes from ANTHROPIC_API_KEY (process, .env or the Windows user environment). It is never printed.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable
from datetime import UTC, datetime

import jsonschema

from . import config


class BudgetExceeded(RuntimeError):
    pass


class NoRecording(RuntimeError):
    pass


def _load_key() -> str | None:
    if os.environ.get("ANTHROPIC_API_KEY"):
        return os.environ["ANTHROPIC_API_KEY"]
    env_file = config.ROOT / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            name, _, value = line.partition("=")
            if name.strip() == "ANTHROPIC_API_KEY" and value.strip():
                return value.strip().strip('"')
    if os.name == "nt":  # variable set in Windows after this terminal was opened
        try:
            import winreg

            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                return winreg.QueryValueEx(k, "ANTHROPIC_API_KEY")[0] or None
        except OSError:
            return None
    return None


class LLM:
    """mode: 'auto' (live if a key exists, else demo), 'live' or 'demo' (replay recordings only)."""

    def __init__(
        self,
        mode: str = "auto",
        max_calls: int = config.MAX_CALLS_PER_RUN,
        recordings=config.RECORDINGS,
        log_dir=config.LOGS,
    ):
        key = None if mode == "demo" else _load_key()
        if mode == "live" and not key:
            raise RuntimeError("Live mode needs ANTHROPIC_API_KEY (environment or .env).")
        self.mode = "live" if key else "demo"
        self.max_calls = max_calls
        self.recordings = recordings
        self.recordings.mkdir(parents=True, exist_ok=True)
        log_dir.mkdir(parents=True, exist_ok=True)
        self.log_path = log_dir / f"run-{datetime.now():%Y%m%d-%H%M%S}.jsonl"
        self.calls = 0
        self.cache_hits = 0
        self.tokens_in = 0
        self.tokens_out = 0
        self._client = None
        if key:
            import anthropic

            self._client = anthropic.Anthropic(api_key=key, timeout=config.TIMEOUT_S, max_retries=config.SDK_RETRIES)

    # ------------------------------------------------------------------ public
    def ask(
        self,
        task: str,
        system: str,
        prompt: str,
        schema: dict,
        check: Callable[[dict], list[str]] | None = None,
        max_tokens: int = 1500,
    ) -> dict:
        """Return a dict that matches `schema` and passes `check` (a list of problems; empty = ok)."""
        # max_tokens is not part of the key: only complete, checked answers are recorded,
        # so a larger output budget cannot change a recorded answer.
        request = {"model": config.MODEL, "system": system, "prompt": prompt, "schema": schema}
        key = hashlib.sha256(json.dumps(request, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:20]
        path = self.recordings / f"{task}-{key}.json"
        if path.exists():
            self.cache_hits += 1
            answer = json.loads(path.read_text(encoding="utf-8"))["answer"]
            self._log(task, key, "recording", 0, 0, [])
            return answer
        if self.mode == "demo":
            raise NoRecording(f"No recorded answer for {task} ({key}); run once with an API key.")

        problems: list[str] = []
        user = prompt
        for attempt in range(config.SCHEMA_RETRIES + 1):
            answer, usage = self._call(system, user, schema, max_tokens)
            problems = self._problems(answer, schema, check)
            self._log(task, key, "api", usage[0], usage[1], problems, attempt)
            if problems == ["max_tokens"]:  # truncated: retry with a larger output budget
                max_tokens = int(max_tokens * 1.5)
            if not problems:
                path.write_text(
                    json.dumps(
                        {
                            "task": task,
                            "model": config.MODEL,
                            "recorded_at": datetime.now(UTC).isoformat(timespec="seconds"),
                            "request": {"system": system, "prompt": prompt},
                            "answer": answer,
                        },
                        ensure_ascii=False,
                        indent=1,
                    ),
                    encoding="utf-8",
                )
                return answer
            user = (
                prompt
                + "\n\nYour previous answer was rejected by the checker:\n- "
                + "\n- ".join(problems)
                + "\nAnswer again, fixing these points."
            )
        raise ValueError(f"{task}: answer failed checks after retries: {problems}")

    def cost_usd(self) -> float:
        p_in, p_out = config.PRICE_PER_MTOK.get(config.MODEL, (0.0, 0.0))
        return (self.tokens_in * p_in + self.tokens_out * p_out) / 1e6

    def summary(self) -> dict:
        try:
            log = str(self.log_path.relative_to(config.ROOT))
        except ValueError:
            log = self.log_path.name
        return {
            "mode": self.mode,
            "model": config.MODEL,
            "api_calls": self.calls,
            "recorded_answers_used": self.cache_hits,
            "input_tokens": self.tokens_in,
            "output_tokens": self.tokens_out,
            "estimated_cost_usd": round(self.cost_usd(), 5),
            "log": log.replace("\\", "/"),
        }

    # ----------------------------------------------------------------- private
    def _call(self, system: str, user: str, schema: dict, max_tokens: int):
        if self.calls >= self.max_calls:
            raise BudgetExceeded(f"Call cap reached ({self.max_calls} per run).")
        self.calls += 1
        response = self._client.messages.create(
            model=config.MODEL,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
            thinking={"type": "disabled"},
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        )
        self.tokens_in += response.usage.input_tokens
        self.tokens_out += response.usage.output_tokens
        usage = (response.usage.input_tokens, response.usage.output_tokens)
        if response.stop_reason == "refusal":
            return {"_error": "refusal"}, usage
        if response.stop_reason == "max_tokens":
            return {"_error": "max_tokens"}, usage
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            return json.loads(text), usage
        except json.JSONDecodeError:
            return {"_error": "invalid JSON"}, usage

    @staticmethod
    def _problems(answer: dict, schema: dict, check) -> list[str]:
        if "_error" in answer:
            return [answer["_error"]]
        try:
            jsonschema.validate(answer, schema)
        except jsonschema.ValidationError as e:
            return [f"schema: {e.message}"]
        return check(answer) if check else []

    def _log(self, task, key, source, tin, tout, problems, attempt=0):
        p_in, p_out = config.PRICE_PER_MTOK.get(config.MODEL, (0.0, 0.0))
        line = {
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            "task": task,
            "request": key,
            "source": source,
            "attempt": attempt,
            "model": config.MODEL,
            "input_tokens": tin,
            "output_tokens": tout,
            "estimated_cost_usd": round((tin * p_in + tout * p_out) / 1e6, 6),
            "problems": problems,
        }
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
