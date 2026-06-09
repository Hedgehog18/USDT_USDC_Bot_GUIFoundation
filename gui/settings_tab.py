from PySide6.QtWidgets import QPushButton, QTextEdit, QVBoxLayout, QWidget

from config.config_manager import ConfigManager


class SettingsTab(QWidget):
    def __init__(self) -> None:
        super().__init__()
        self.config = ConfigManager().config

        self.output = QTextEdit()
        self.output.setReadOnly(True)

        self.refresh_button = QPushButton("Refresh Settings")
        self.refresh_button.clicked.connect(self.refresh)

        layout = QVBoxLayout()
        layout.addWidget(self.refresh_button)
        layout.addWidget(self.output)
        self.setLayout(layout)

        self.refresh()

    def refresh(self) -> None:
        self.config = ConfigManager().config
        lines = [
            "=== General ===",
            f"Mode: {self._value('mode')}",
            f"Symbol: {self._value('symbol')}",
            f"Database path: {self._value('database_path')}",
            "",
            "=== Market Data ===",
            f"Market data source: {self._value('market_data_source')}",
            f"Use real market data: {self._value('use_real_market_data')}",
            f"Binance base URL: {self._value('binance_base_url')}",
            f"Cache TTL seconds: {self._value('market_data_cache_ttl_seconds')}",
            f"Order book limit: {self._value('order_book_limit')}",
            f"Trade history limit: {self._value('trade_history_limit')}",
            "",
            "=== Trading ===",
            f"Trade size percent: {self._value('trade_size_percent')}",
            f"Target profit: {self._value('target_profit')}",
            f"Max active cycles: {self._value('max_active_cycles')}",
            f"USDT reserve percent: {self._value('min_usdt_reserve_percent')}",
            f"USDC reserve percent: {self._value('min_usdc_reserve_percent')}",
            f"Price tick size: {self._value('price_tick_size')}",
            f"Quantity step size: {self._value('quantity_step_size')}",
            f"Min notional: {self._value('min_notional')}",
            "",
            "=== Strategy Windows ===",
            f"Work window minutes: {self._value('work_window_minutes')}",
            f"Short window minutes: {self._value('short_window_minutes')}",
            f"Long window minutes: {self._value('long_window_minutes')}",
            f"Volatility window: {self._value('volatility_window')}",
            "",
            "=== Risk / Filters ===",
            f"Min market activity score: {self._value('min_market_activity_score')}",
            f"Min cycle prediction score: {self._value('min_cycle_prediction_score')}",
            f"Buy zone max: {self._value('buy_zone_max')}",
            f"Sell zone min: {self._value('sell_zone_min')}",
            f"Max allowed spread: {self._value('max_allowed_spread')}",
            f"Min liquidity score: {self._value('min_liquidity_score')}",
            f"Min market health score: {self._value('min_market_health_score')}",
            "",
            "=== Fees ===",
            f"Maker fee percent: {self._value('maker_fee_percent')}",
            f"Taker fee percent: {self._value('taker_fee_percent')}",
            "",
            "=== Runner ===",
            f"Runner interval seconds: {self._value('runner_interval_seconds')}",
            f"Max runner iterations: {self._value('max_runner_iterations')}",
            "",
            "=== Backtest ===",
            f"Backtest interval: {self._value('backtest_interval')}",
            f"Backtest limit: {self._value('backtest_limit')}",
            f"Backtest initial USDT: {self._value('backtest_initial_usdt')}",
            f"Backtest initial USDC: {self._value('backtest_initial_usdc')}",
            "",
            "=== Paper Safety ===",
            f"Paper max drawdown: {self._value('paper_max_drawdown')}",
            f"Paper max losing cycles: {self._value('paper_max_losing_cycles')}",
            f"Paper min portfolio value: {self._value('paper_min_portfolio_value')}",
            "",
            "=== Logging ===",
            f"Log file path: {self._value('log_file_path')}",
            f"Log level: {self._value('log_level')}",
        ]
        self.output.setPlainText("\n".join(lines))

    def _value(self, name: str, default: str = "N/A") -> str:
        value = getattr(self.config, name, default)
        if self._is_sensitive_name(name):
            return self._mask_sensitive(str(value))
        return str(value)

    @staticmethod
    def _is_sensitive_name(name: str) -> bool:
        lowered = name.lower()
        return any(token in lowered for token in ("api_key", "api_secret", "secret", "token"))

    @staticmethod
    def _mask_sensitive(value: str) -> str:
        if not value or value == "N/A":
            return value
        if len(value) <= 8:
            return "***"
        return f"{value[:4]}...{value[-4:]}"
