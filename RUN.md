# Як запустити проєкт

## 1. Створити віртуальне оточення

```bash
python -m venv .venv
```

## 2. Активувати оточення

Windows PowerShell:

```bash
.venv\Scripts\Activate.ps1
```

Windows CMD:

```bash
.venv\Scripts\activate.bat
```

## 3. Встановити залежності

```bash
pip install -r requirements.txt
```

## 4. Запустити MVP

```bash
python main.py
```

## 5. Запустити тести

```bash
pytest
```

## Поточний режим

На цьому етапі проєкт працює в DEMO/read-only режимі:
- реальні ордери не створюються;
- Binance використовується тільки для читання market data;
- Demo-цикли, сигнали, аудит, статистика й повідомлення зберігаються в SQLite.


## Оновити структуру SQLite вручну

```bash
python migrate_db.py
```


## Перевірити готовність системи

```bash
python health_check.py
```


## Логи

Основний лог-файл:

```text
logs/bot.log
```


## Управління через CLI

```bash
python manage.py health
python manage.py migrate
python manage.py run --iterations 3 --interval 10
python manage.py stats
python manage.py notifications --limit 10
python manage.py notifications --mark-read
python manage.py audit --limit 10
```


## Backtest

```bash
python manage.py backtest --interval 1m --limit 500
```


## Backtest-звіти

```bash
python manage.py backtest-runs --limit 10
```

CSV-звіти зберігаються у папці:

```text
reports/
```


## Порівняння backtest-запусків

```bash
python manage.py backtest-compare --limit 20
python manage.py backtest-compare --limit 20 --export
```


## Підбір параметрів

```bash
python manage.py parameter-sweep --interval 1m --limit 500 --target-profits 0.0001,0.0002,0.0003 --trade-sizes 0.05,0.10,0.15 --top 10
python manage.py parameter-sweep --interval 1m --limit 500 --export
```


## Walk-forward перевірка

```bash
python manage.py walk-forward --interval 1m --limit 1000 --train-size 300 --test-size 100
python manage.py walk-forward --interval 1m --limit 1000 --train-size 300 --test-size 100 --export
```


## Історія walk-forward запусків

```bash
python manage.py walk-forward-runs --limit 10
```

Backtest-звіт тепер також показує Sharpe, Sortino, Profit Factor і Expectancy.


## Backtest period analytics

```bash
python manage.py backtest-periods 1
```

Backtest тепер створює TXT-файл з автоматичними insights у reports/.


## Paper Trading

```bash
python manage.py paper-sim --iterations 5
python manage.py paper-orders --limit 20
```


## Paper Cycles

```bash
python manage.py paper-cycle-sim --iterations 10
python manage.py paper-cycles --limit 20
```


## Paper Analytics та Safety

```bash
python manage.py paper-stats --limit 100
python manage.py paper-safety --limit 20
```


## Paper Report

```bash
python manage.py paper-report --limit 500
```


## Paper State / Recovery

```bash
python manage.py paper-recovery
python manage.py paper-states --limit 20
```


## Paper Run History

```bash
python manage.py paper-runs --limit 20
```


## GUI

```bash
python gui_app.py
```

Або:

```bash
python manage.py gui
```
