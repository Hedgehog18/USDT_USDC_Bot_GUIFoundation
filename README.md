# USDT/USDC Market-Making Bot MVP

Поточний етап:
- Demo execution через bid/ask;
- SQLite;
- RecoveryManager;
- read-only Binance market data через REST API.

## Запуск

```bash
pip install -r requirements.txt
python main.py
```

Увага: на цьому етапі бот не створює реальні ордери.

- PortfolioAnalytics: realized profit, win rate, ROI.

- StatisticsEngine: агрегована статистика по циклах і сигналах.

- BotStateManager: формальні стани INIT / RECOVERY / READY / RUNNING_DEMO / SAFE_WAIT / ERROR.

- NotificationEngine: центр повідомлень INFO / IMPORTANT / WARNING / CRITICAL.

- AuditEngine: збереження пояснень рішень у decision_audit.

- ConfigManager: завантаження параметрів із config/settings.json.

- ExchangeRulesEngine: tick size, step size, min notional, profitability after rounding.

- FeeEngine: gross profit, fees, net profit.

- MarketDataCache: TTL-кеш для Binance REST market data.

- BotRunner: періодичний запуск Demo-аналізу кожні N секунд із max_iterations.

- OrderBookEngine: аналіз bid/ask liquidity imbalance.
- TradeHistoryEngine: аналіз останніх угод і micro trend.
- VolatilityEngine: оцінка режиму волатильності.

- DecisionEngine now uses order book pressure, micro trend and volatility filters.

- MarketHealthEngine: spread/liquidity/volatility health gate before decisions.

- DatabaseMigrationManager: безпечне додавання нових колонок у SQLite через легкі міграції.

- HealthCheck: стартова перевірка config / SQLite / Binance read-only.

- AppLogger: файлові логи logs/bot.log з ротацією.

- manage.py: CLI для run / health / migrate / stats / notifications / audit.

- BacktestEngine: історичний read-only backtest на Binance klines.

- BacktestReportExporter: збереження backtest summary/trades у CSV.
- Backtest results storage: backtest_runs і backtest_trades у SQLite.

- BacktestComparisonEngine: рейтинг і порівняння історичних backtest-запусків.
- BacktestComparisonExporter: CSV-експорт порівняння запусків.

- ParameterSweepEngine: серійний backtest для підбору target_profit і trade_size_percent.
- ParameterSweepExporter: CSV-експорт parameter sweep.

- WalkForwardEngine: train/test перевірка параметрів проти overfitting.
- WalkForwardExporter: CSV-експорт walk-forward результатів.

- Walk-forward storage: walk_forward_runs і walk_forward_windows у SQLite.

- BacktestMetricsEngine: equity returns, Sharpe, Sortino, Profit Factor, Expectancy.

- EquityAnalyticsEngine: equity curve і period analytics для backtest.
- Backtest equity/period storage: backtest_equity_points і backtest_period_analytics.

- BacktestInsightsEngine: автоматичні висновки по backtest результату.
- BacktestInsightsExporter: TXT-звіт з сильними/слабкими сторонами і next steps.

- PaperExchange / PaperOrderManager / PaperPortfolioManager: перший шар paper trading без реальних коштів.

- PaperCycleManager: paper open/close цикли з PnL і збереженням у SQLite.

- PaperAnalyticsEngine: статистика paper cycles.
- PaperSafetyEngine: paper kill-switch правила drawdown/loss streak/min portfolio value.

- PaperTradingEngine: orchestrator paper-режиму для CLI/GUI.
- PaperReportExporter: CSV-звіти по paper cycles, safety і summary.

- PaperStateManager: формальні стани paper режиму INIT/READY/RUNNING/SAFE_STOP/STOPPED/ERROR.
- PaperRecoveryManager: відновлення snapshot portfolio/open cycles після перезапуску.

- PaperInsightsEngine: автоматичні висновки по paper-run.
- Paper run storage: paper_runs у SQLite та paper-runs CLI.

- PySide6 GUI foundation: Dashboard / Health / Backtest / Paper Trading / Logs.
