# USDT/USDC Bot GUI Foundation

USDT/USDC Bot GUI Foundation is an MVP trading-bot workspace for DEMO, paper trading, backtesting, diagnostics, and analytics around the USDCUSDT pair.

The current GUI MVP is focused on safe observation and simulation:

- no real trading is enabled;
- Binance is used only for read-only market data;
- Demo Runner uses the existing `BotRunner` / `BotEngine` flow;
- backtest and paper trading results are stored in SQLite;
- reports are exported to `reports/`;
- logs are written to `logs/bot.log`.

## Install

Create and activate a virtual environment:

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
python -m pip install -r requirements.txt
```

## Run GUI

```bash
python gui_app.py
```

Or through the CLI entrypoint:

```bash
python manage.py gui
```

## Run Tests

```bash
python -m pytest
```

## GUI Tabs

- Dashboard: system summary, database counters, latest backtest and paper results.
- Health: config, SQLite, and market-data readiness checks.
- Backtest: run historical backtests from the GUI and view recent runs.
- Paper Trading: run paper simulation and inspect paper runs/cycles.
- Analytics: equity curve, drawdown curve, and trade PnL distribution for the latest backtest.
- Runner: monitor and control the Demo Runner with guarded Start/Stop controls.
- Logs: file log and system event diagnostics with filters.
- Settings: read-only config view.

## Useful CLI Commands

```bash
python manage.py health
python manage.py run --iterations 3 --interval 10
python manage.py backtest --interval 1m --limit 500
python manage.py paper-cycle-sim --iterations 5
python manage.py paper-runs --limit 20
python manage.py paper-stats --limit 100
python manage.py paper-safety --limit 20
```

## Safety Notice

Real trading is not enabled in this GUI MVP checkpoint. Do not use this project for live order placement without a separate real-trading implementation, dedicated risk controls, API-key management, and review.
