# Long Paper Run Workflow

Long Paper Run is a validation workflow for extended paper/demo testing before any real trading.

Real trading is disabled. This workflow does not place Binance orders and does not change the strategy, DecisionEngine, or RiskManager.

## CLI

Run a long paper validation from the command line:

```bash
python manage.py long-paper-run --iterations 500 --interval 5
```

For a quick smoke check:

```bash
python manage.py long-paper-run --iterations 5 --interval 1
```

The command runs the existing `PaperTradingEngine`, then prints:

- paper run summary;
- paper stats;
- paper insights;
- validation summary;
- paths to generated reports in `reports/`.

## GUI

Open the GUI:

```bash
python gui_app.py
```

or:

```bash
python manage.py gui
```

Go to `Paper Trading` and use the `Long Paper Run` section:

- set `Iterations`;
- set `Interval seconds`;
- click `Start Long Paper Run`.

The GUI runs the workflow in a background thread so the interface remains responsive.

## Metrics To Watch

Review these outputs after each run:

- closed paper cycles;
- paper win rate;
- paper net profit;
- profit factor;
- safety stops;
- paper insights rating;
- validation summary status;
- risk blocked rate;
- decision diagnostics WAIT/BUY/SELL reasons.

Generated reports:

- `reports/paper_cycles_report.csv`;
- `reports/paper_safety_report.csv`;
- `reports/paper_summary_report.csv`;
- `reports/paper_run_<id>_insights.txt`.

## When Not To Move Toward Real Trading

Do not move toward real trading if any of these are true:

- validation status is `NO_DATA`, `WEAK`, or `MIXED`;
- paper run has no closed cycles;
- paper net profit is not positive;
- risk blocked rate is very high;
- paper safety stops are frequent;
- backtest has no trades or negative net profit;
- decision diagnostics show mostly WAIT with low confidence;
- results are based on only a small number of iterations.

Before real trading is even considered, run longer paper validation and review the diagnostics manually.
