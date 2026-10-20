# Runbook

## Run

```
pip install -r requirements.txt
python demo.py            # full example on the synthetic portfolio, no API key needed
python -m pytest -q       # offline tests
```

Outputs: `final-report.pdf` at the root; `output/land_portfolio.xlsx`, `output/dashboard.html`, `output/memos.md`
and `output/summary.json`.

## Updating with new data

- **Change an assumption** (tax rate, building cost, sales speed, interest): edit `land_deals/config.py`. Each line
  has the base value, the low and high values used in the bad and good cases, and its source. Then run
  `python -m land_deals run`.
- **Change one plot only**: add the value under `overrides` for that plot in `data/portfolio.json`
  (for example `"infra_per_m2": 150`).
- **Add a plot from a description**: write the description in a text file and run
  `python -m land_deals intake path/to/plot.txt`. Check the values it prints (each one shows the sentence it came
  from); if they are right, run it again with `--accept` to add the plot.
- **Use your own portfolio**: replace `data/portfolio.json` with your plots (same fields as the example) and run
  `python -m land_deals run`.

Reading descriptions and writing the investment notes need `ANTHROPIC_API_KEY` (or a `.env` file, see
`.env.example`) the first time a question is asked; answers are saved in `data/recorded/` and never paid twice.
`python -m land_deals run --no-memos` builds everything except the notes, with no AI at all.

## Publishing the live demo

Every push to `main` runs `.github/workflows/pages.yml`: tests, then `python demo.py --demo` with an empty API key (no
call is made), then the dashboard is published as the GitHub Pages site, with the PDF next to it. One-time setup in the
repository: Settings > Pages > Source = GitHub Actions. If that is not set, the workflow stops at "configure-pages"
with a clear message.

## When something breaks

| Message or symptom | What to do |
|---|---|
| `No portfolio yet` | Run `python generate_data.py`, or put your own `data/portfolio.json` in place |
| `No recorded answer ... run once with an API key` | A plot or description changed, so its question is new. Set `ANTHROPIC_API_KEY`, or use `--no-memos` |
| `Call cap reached` | The run hit the limit of AI calls (`LAND_MAX_CALLS`, default 20). Run again; saved answers are not paid twice |
| A note says `rejected by the checks` | The AI quoted a number the model did not compute, twice. The note is left out; the numbers in the report are unaffected |
| `fix the problems before accepting` (intake) | A value was missing or not found in the text. Correct the description, or edit the plot in `data/portfolio.json` by hand |
| The Excel charts show no axes | Open the file in a recent Excel or LibreOffice; the file sets the axes to visible |
| Tests fail after changing an assumption | Some tests check directions (higher cost, lower value); a failing one usually means a sign or unit slipped in `config.py` |

Each AI call is logged as one line in `output/logs/` with tokens and estimated cost.
