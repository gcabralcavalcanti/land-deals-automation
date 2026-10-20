# land-deals-automation

Public version, with synthetic numbers, of the kind of analysis I did when buying and selling land: whether a plot is
worth buying, whether it pays to split it into lots or sell it whole, and how long until the money comes back.

![Synthetic data — no private records](https://img.shields.io/badge/data-synthetic%20%E2%80%94%20no%20private%20records-e07b39)
![Built with AI assistance](https://img.shields.io/badge/built%20with-AI%20assistance-6f42c1)

![Dashboard](docs/dashboard.jpg)

## What it shows

- Every cost and every payment on a monthly calendar: purchase taxes, approvals, streets and utilities, upkeep,
  sales over the years and installments, so the time the money stays tied up is visible.
- For each plot: value created, return per year, the most cash needed at one time and the month the money is back,
  in a bad, an expected and a good case ([`final-report.pdf`](final-report.pdf)).
- An investment note per plot written by Claude, kept only if every number in it matches the model.

## How I use it

This model is new: I built it for this portfolio, and it does not replace a routine I run today. It puts into code the
questions I worked through on each land deal: what the plot really costs to buy and hold, whether splitting it into
lots pays more than selling it whole, how much cash goes in before sales start, and when the money comes back. The way
I would use it is one deal at a time: describe the plot in a text file, check the inputs the AI pulls out, run the
model, and read the numbers and the note before deciding. Nothing runs on a schedule, and the inputs only enter the
model after I accept them.

## Run it

```
pip install -r requirements.txt
python demo.py
```

Runs without an API key, replaying recorded answers. Set `ANTHROPIC_API_KEY` to call Claude live.

## More

- [How it works](docs/how-it-works.md): the steps, the results on the made-up portfolio, the commands.
- [Runbook](RUNBOOK.md): changing assumptions, adding a plot, and what to do when something breaks.

## Limits

- Costs marked "illustrative" are typical values, not quotes; a real decision needs real budgets and local prices.
- Lots sell at an even pace; there is no launch rush or real sales history.
- Synthetic plots and prices only.

## How AI was used

I use Claude (Claude Code and the API) for coding, review and documentation. The questions, modelling choices,
validation and conclusions are mine.

MIT License.
