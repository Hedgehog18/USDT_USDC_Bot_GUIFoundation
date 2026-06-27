# CLI команди USDT/USDC Bot

Цей файл містить довідник по командах `python manage.py ...`, згрупований за призначенням.

Важливо: real trading у проєкті вимкнений. Команди, пов'язані з runner, paper, diagnostics, backtest та high-frequency research, призначені для DEMO/PAPER режиму, досліджень і dry-run аналізу.

## Базові команди

| Команда | Призначення | Приклад |
|---|---|---|
| `run` | Запускає основний demo runner через CLI. | `python manage.py run --iterations 5 --interval 10` |
| `health` | Перевіряє готовність системи: конфіг, базу, логування та базові залежності. | `python manage.py health` |
| `migrate` | Запускає SQLite міграції та оновлення структури БД. | `python manage.py migrate` |
| `stats` | Показує базову статистику системи з SQLite. | `python manage.py stats` |
| `gui` | Запускає PySide6 GUI. | `python manage.py gui` |

## Дані, джерела та комісії

| Команда | Призначення | Приклад |
|---|---|---|
| `data-source-check` | Перевіряє поточний source ринкових даних, Binance health-check, останню ціну та fallback/mock стан. | `python manage.py data-source-check` |
| `fee-model-report` | Показує configured/effective fee model, приклади розрахунку комісій і consistency check. | `python manage.py fee-model-report` |

## Strategy diagnostics

| Команда | Призначення | Приклад |
|---|---|---|
| `strategy-report` | Показує загальний strategy validation summary: сигнали, BUY/SELL, confidence, spread, volatility, market regime. | `python manage.py strategy-report` |
| `strategy-tuning-report` | Dry-run аналіз того, скільки сигналів пройшло б при м'якших confidence thresholds. | `python manage.py strategy-tuning-report` |
| `strategy-profile-sim` | Симулює strategy profile по збережених market snapshots без створення угод. | `python manage.py strategy-profile-sim --profile mean_reversion_v2_small_target` |
| `confidence-diagnostics` | Аналізує confidence: min/max/average/median, buckets, WAIT reasons, center distance statistics. | `python manage.py confidence-diagnostics` |
| `entry-zone-diagnostics` | Перевіряє, чи ціна потрапляла у BUY/SELL зони та як розподілений work_position. | `python manage.py entry-zone-diagnostics` |
| `filter-pass-diagnostics` | Показує, які фільтри блокують entry-zone samples. | `python manage.py filter-pass-diagnostics` |
| `decision-diagnostics` | Аналізує BUY/SELL/WAIT рішення, топ причин і confidence distribution. | `python manage.py decision-diagnostics` |
| `risk-diagnostics` | Аналізує risk audit: allowed/blocked, blocked rate, top risk reasons, latest blocked decisions. | `python manage.py risk-diagnostics` |
| `risk-profitability-diagnostics` | Пояснює profitability blockers: gross, fees, net, rounding impact для risk checks. | `python manage.py risk-profitability-diagnostics` |
| `validation-summary` | Дає єдиний статус валідації стратегії: NO_DATA, WEAK, MIXED, PROMISING, READY_FOR_LONG_PAPER. | `python manage.py validation-summary --profile mean_reversion_v2_small_target` |
| `profile-performance-summary` | Підсумовує performance профілю з окремим accounting для automatic і manual closes. | `python manage.py profile-performance-summary --profile mean_reversion_v2_small_target` |

## Order book та center confidence diagnostics

| Команда | Призначення | Приклад |
|---|---|---|
| `order-book-diagnostics` | Аналізує order_book_pressure distribution, BUY/SELL-zone pressure та latest entry-zone snapshots. | `python manage.py order-book-diagnostics` |
| `order-book-rule-sim` | Dry-run порівняння strict, allow_balanced, contrarian та ignore order book правил. | `python manage.py order-book-rule-sim` |
| `center-confidence-diagnostics` | Пояснює LOW/MEDIUM/HIGH center confidence, center alignment і distance між centers. | `python manage.py center-confidence-diagnostics` |
| `center-confidence-rule-sim` | Dry-run симуляція м'якших правил center confidence. | `python manage.py center-confidence-rule-sim` |
| `combined-entry-rule-sim` | Dry-run комбінованих entry rules: center confidence + order book + safety filters. | `python manage.py combined-entry-rule-sim` |

## Sensitivity diagnostics

| Команда | Призначення | Приклад |
|---|---|---|
| `entry-threshold-sensitivity` | Перевіряє альтернативні BUY/SELL thresholds для entry zones. | `python manage.py entry-threshold-sensitivity --profile mean_reversion_v2_small_target` |
| `micro-trend-sensitivity` | Порівнює strict, allow_neutral та ignore micro trend режими. | `python manage.py micro-trend-sensitivity --profile mean_reversion_v2_small_target` |
| `target-profit-sensitivity` | Dry-run аналіз target_profit values для відкритих або історичних cycles. | `python manage.py target-profit-sensitivity --profile mean_reversion_v2_small_target` |
| `partial-target-diagnostics` | Перевіряє lower/partial target multipliers: 25%, 50%, 75%, 100%. | `python manage.py partial-target-diagnostics --profile mean_reversion_v2` |
| `exit-tolerance-sim` | Dry-run close tolerance simulation для near-target open cycles. | `python manage.py exit-tolerance-sim --profile mean_reversion_v2_small_target` |

## Backtest

| Команда | Призначення | Приклад |
|---|---|---|
| `backtest` | Запускає історичний backtest по Binance candles. | `python manage.py backtest --interval 1m --limit 500` |
| `backtest-runs` | Показує останні backtest runs з SQLite. | `python manage.py backtest-runs --limit 20` |
| `backtest-periods` | Показує period analytics для конкретного backtest run. | `python manage.py backtest-periods 1` |
| `backtest-compare` | Порівнює кілька backtest runs і може експортувати CSV. | `python manage.py backtest-compare --limit 5 --export` |
| `parameter-sweep` | Запускає серію backtests для підбору параметрів. | `python manage.py parameter-sweep --interval 1m --limit 500` |
| `walk-forward` | Запускає walk-forward validation. | `python manage.py walk-forward --train-size 300 --test-size 100 --export` |
| `walk-forward-runs` | Показує історію walk-forward runs. | `python manage.py walk-forward-runs --limit 20` |

## Paper trading та paper validation

| Команда | Призначення | Приклад |
|---|---|---|
| `paper-sim` | Запускає коротку paper simulation. | `python manage.py paper-sim --iterations 10` |
| `paper-cycle-sim` | Запускає paper cycle simulation через існуючий paper engine. | `python manage.py paper-cycle-sim --iterations 20 --profile mean_reversion_v2_small_target` |
| `long-paper-run` | Запускає довший paper validation workflow з підсумками та reports. | `python manage.py long-paper-run --iterations 500 --interval 1 --profile mean_reversion_v2_small_target` |
| `long-paper-runs` | Показує історію long paper runs. | `python manage.py long-paper-runs --limit 20` |
| `collect-closed-cycles` | Запускає collection watcher до досягнення потрібної кількості CLOSED cycles. | `python manage.py collect-closed-cycles --profile mean_reversion_v2_small_target --target 100 --interval 1` |
| `paper-orders` | Показує останні paper orders. | `python manage.py paper-orders --limit 20` |
| `paper-cycles` | Показує останні paper cycles. | `python manage.py paper-cycles --limit 20` |
| `paper-open-cycles` | Показує diagnostics для OPEN paper cycles. | `python manage.py paper-open-cycles` |
| `paper-close-cycle` | Ручно закриває OPEN paper cycle по поточній Binance ціні. | `python manage.py paper-close-cycle --db-id 9 --reason stale` |
| `paper-close-watch` | Періодично моніторить OPEN cycles і повідомляє про close_condition_met. | `python manage.py paper-close-watch --profile mean_reversion_v2_small_target --interval 60 --max-checks 480` |
| `paper-stats` | Показує paper trading statistics. | `python manage.py paper-stats --limit 100` |
| `paper-safety` | Показує paper safety events. | `python manage.py paper-safety --limit 20` |
| `paper-report` | Створює CSV/TXT paper report. | `python manage.py paper-report --limit 500` |
| `paper-recovery` | Показує paper recovery snapshot. | `python manage.py paper-recovery` |
| `paper-states` | Показує paper state transitions. | `python manage.py paper-states --limit 20` |
| `paper-runs` | Показує історію paper runs. | `python manage.py paper-runs --limit 20` |

## Paper exit та path diagnostics

| Команда | Призначення | Приклад |
|---|---|---|
| `direction-outcome-diagnostics` | Перевіряє, чи ціна після entry рухалась у правильному напрямку. | `python manage.py direction-outcome-diagnostics --profile mean_reversion_v2_small_target` |
| `holding-horizon-diagnostics` | Оцінює, скільки snapshots/часу потрібно для досягнення target. | `python manage.py holding-horizon-diagnostics --profile mean_reversion_v2` |
| `post-entry-path-diagnostics` | Показує шлях ціни після entry candidate: next prices, favorable/adverse moves, target hit. | `python manage.py post-entry-path-diagnostics --profile mean_reversion_v2` |
| `entry-confirmation-diagnostics` | Dry-run перевірка confirmation variants перед входом. | `python manage.py entry-confirmation-diagnostics --profile mean_reversion_v2` |
| `exit-risk-diagnostics` | Аналізує stop-loss і max holding risk для open/closed cycles. | `python manage.py exit-risk-diagnostics --profile mean_reversion_v2_small_target` |
| `max-holding-sensitivity` | Dry-run sensitivity для max holding time. | `python manage.py max-holding-sensitivity --profile mean_reversion_v2_small_target` |
| `exit-rule-sim` | Dry-run порівняння exit rules: stop loss, max holding, комбіновані варіанти. | `python manage.py exit-rule-sim --profile mean_reversion_v2_small_target` |
| `exit-rule-optimizer` | Оптимізує dry-run exit rule scenarios для stale cycles. | `python manage.py exit-rule-optimizer --profile mean_reversion_v2_small_target` |

## Trend, range та session diagnostics

| Команда | Призначення | Приклад |
|---|---|---|
| `trend-alignment-diagnostics` | Аналізує alignment entry з 1h trend для open/history cycles. | `python manage.py trend-alignment-diagnostics --profile mean_reversion_v2_small_target` |
| `trend-filter-sim` | Dry-run симуляція 1h trend filter scenarios. | `python manage.py trend-filter-sim --profile mean_reversion_v2_small_target` |
| `trend-strength-diagnostics` | Аналізує силу 1h trend, slope, range position та weak FLAT thresholds. | `python manage.py trend-strength-diagnostics --profile mean_reversion_v2_small_target` |
| `range-shift-diagnostics` | Перевіряє, чи завислі cycles виникають після зміщення робочого коридору. | `python manage.py range-shift-diagnostics --profile mean_reversion_v2_small_target` |
| `target-rebase-diagnostics` | Dry-run rebase target scenarios для stalled/open cycles. | `python manage.py target-rebase-diagnostics --profile mean_reversion_v2_small_target` |
| `break-even-rebase-sim` | Dry-run break-even rebase scenarios. | `python manage.py break-even-rebase-sim --profile mean_reversion_v2_small_target` |
| `market-session-diagnostics` | Аналізує paper cycle performance по сесіях: ASIA, LONDON, NEW_YORK, overlap. | `python manage.py market-session-diagnostics --profile mean_reversion_v2_small_target` |
| `session-filter-sim` | Dry-run session filter scenarios. | `python manage.py session-filter-sim --profile mean_reversion_v2_small_target` |

## Profile comparison

| Команда | Призначення | Приклад |
|---|---|---|
| `profile-comparison-diagnostics` | Порівнює mean-reversion profile variants за candidates, hit rate, рухом ціни та score. | `python manage.py profile-comparison-diagnostics` |

## High Frequency research

| Команда | Призначення | Приклад |
|---|---|---|
| `collect-market-snapshots` | Збирає live HF market snapshots у `market_snapshots_hf` без торгівлі та paper cycles. | `python manage.py collect-market-snapshots --duration-hours 24 --interval 5` |
| `high-frequency-dataset-summary` | Показує summary для HF dataset: snapshots, micro-entry count, blockers, distributions. | `python manage.py high-frequency-dataset-summary` |
| `high-frequency-diagnostics` | Оцінює high-frequency потенціал по HF або звичайних market snapshots. | `python manage.py high-frequency-diagnostics` |
| `micro-cycle-sim` | Dry-run симулятор micro-cycles по HF snapshots з одним active cycle одночасно. `--target` приймає будь-яке додатне decimal значення у відсотках. | `python manage.py micro-cycle-sim --scenario short_term_mean_reversion --target 0.0005 --max-holding-seconds 180` |
| `micro-cycle-grid-search` | Автоматичний dry-run grid search по scenario, target і max holding для пошуку high-frequency micro-cycle параметрів. | `python manage.py micro-cycle-grid-search --scenario short_term_mean_reversion --top 20 --export-csv reports/micro_cycle_grid_search.csv` |
| `target-resolution-diagnostics` | Перевіряє, чи різні micro-cycle target-и не стають фактично еквівалентними через tick size, rounding, epsilon або дискретність HF snapshots. | `python manage.py target-resolution-diagnostics --compare-simulation 0.0005 0.00075` |

## ML research

| Команда | Призначення | Приклад |
|---|---|---|
| `build-ml-dataset` | Експортує supervised CSV dataset для майбутнього ML research. | `python manage.py build-ml-dataset --symbol USDCUSDT --interval 1m --limit 5000 --profile mean_reversion_v2_small_target --dataset-mode no_micro_trend` |
| `ml-dataset-coverage` | Пояснює, чому dataset має мало або 0 candidate rows. | `python manage.py ml-dataset-coverage --symbol USDCUSDT --interval 1m --limit 1000 --profile mean_reversion_v2_small_target --dataset-mode no_micro_trend` |
| `ml-dataset-summary` | Аналізує готовий ML CSV: positive rate, direction distribution, buckets, hour of day. | `python manage.py ml-dataset-summary --file data/ml/usdcusdt_1m_mean_reversion_v2_small_target_no_micro_trend.csv` |
| `train-ml-baseline` | Навчає offline baseline модель для аналізу, без інтеграції в trading runtime. | `python manage.py train-ml-baseline --file data/ml/usdcusdt_1m_mean_reversion_v2_small_target_no_micro_trend.csv` |

## Notifications та audit

| Команда | Призначення | Приклад |
|---|---|---|
| `notifications` | Показує останні notifications. | `python manage.py notifications --limit 20` |
| `audit` | Показує останні audit записи. | `python manage.py audit --limit 20` |
