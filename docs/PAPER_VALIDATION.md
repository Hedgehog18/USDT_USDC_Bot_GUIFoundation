# Paper Validation Workflow

This document describes the GUI MVP paper/demo validation workflow.

## Safety Boundary

Real trading is not allowed in this checkpoint.

- Do not add Binance API keys.
- Do not place live Binance orders.
- Use only DEMO, paper trading, backtest, and read-only market data.

## Run Paper Cycle Simulation From GUI

1. Start the GUI:

   ```bash
   python gui_app.py
   ```

2. Open the `Paper Trading` tab.
3. Set `Iterations`.
4. Click `Start Paper Simulation`.
5. Review:
   - opened cycles;
   - closed cycles;
   - safety stops;
   - final value;
   - latest Paper Insights.
6. Click `Export Paper Report` to create CSV reports in `reports/`.

CLI equivalent:

```bash
python manage.py paper-cycle-sim --iterations 10
python manage.py paper-report --limit 500
python manage.py paper-runs --limit 20
```

## Run Demo Runner

1. Start the GUI.
2. Open the `Runner` tab.
3. Confirm the warning: `Real trading disabled. Demo/Paper mode only.`
4. Set `Iterations` and `Interval seconds`.
5. Click `Start Demo Runner`.
6. Use `Stop Runner` to request a safe stop after the current iteration.

CLI equivalent:

```bash
python manage.py run --iterations 3 --interval 10
```

## Metrics To Watch

Paper validation should focus on:

- closed cycles count;
- win rate;
- net profit;
- profit factor;
- average net profit;
- safety stop count;
- final portfolio value;
- latest Paper Insights rating and summary;
- consistency between paper results and backtest/analytics.

## Good Paper Result Signals

A good or promising paper result usually has:

- enough closed cycles to be meaningful;
- positive net profit;
- win rate above roughly 60%;
- profit factor above 1.5;
- no repeated safety stops;
- stable or improving final portfolio value;
- Paper Insights rating `GOOD` or `PROMISING`.

## Bad Paper Result Signals

A weak paper result usually has:

- no closed cycles after many iterations;
- negative net profit;
- win rate below roughly 45%;
- profit factor below 1.0;
- repeated safety stops;
- falling portfolio value;
- Paper Insights rating `WEAK`, `MIXED`, or `NO_CLOSED_CYCLES` after a long run.

## Next Step Before Real Trading

Do not move to real trading from this checkpoint. Before any real-trading work, add separate API-key management, real-order safeguards, position limits, dry-run confirmations, and a dedicated review pass.
