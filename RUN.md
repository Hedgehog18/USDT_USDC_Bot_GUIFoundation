# Run Guide

## Setup

```bash
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

## GUI

Start the GUI directly:

```bash
python gui_app.py
```

Start the GUI through `manage.py`:

```bash
python manage.py gui
```

## Tests

```bash
python -m pytest
```

## Core CLI

```bash
python manage.py health
python manage.py migrate
python manage.py run --iterations 3 --interval 10
python manage.py stats
python manage.py notifications --limit 10
python manage.py audit --limit 10
```

## Backtest

Run a backtest:

```bash
python manage.py backtest --interval 1m --limit 500
```

View recent runs and analytics:

```bash
python manage.py backtest-runs --limit 20
python manage.py backtest-periods 1
python manage.py backtest-compare --limit 20
python manage.py backtest-compare --limit 20 --export
```

Backtest CSV/TXT reports are written to:

```text
reports/
```

## Paper Trading

Run paper simulation:

```bash
python manage.py paper-cycle-sim --iterations 5
```

Inspect paper data:

```bash
python manage.py paper-runs --limit 20
python manage.py paper-cycles --limit 20
python manage.py paper-stats --limit 100
python manage.py paper-safety --limit 20
python manage.py paper-report --limit 500
python manage.py paper-recovery
python manage.py paper-states --limit 20
```

## Runner

Run the Demo Runner from CLI:

```bash
python manage.py run --iterations 3 --interval 10
```

Run the Demo Runner from GUI:

1. Open `python gui_app.py`.
2. Go to `Runner`.
3. Set `Iterations` and `Interval seconds`.
4. Click `Start Demo Runner`.
5. Use `Stop Runner` to request a safe stop after the current iteration.

Runner controls are guarded by GUI status: `IDLE`, `RUNNING`, `STOPPING`, `FINISHED`, `ERROR`.

## Logs And Reports

Main log file:

```text
logs/bot.log
```

SQLite diagnostics are available in the GUI `Logs` tab.

Generated reports are stored in:

```text
reports/
```

## Safety Notice

This checkpoint is DEMO / paper / backtest only. Real trading is not enabled.
