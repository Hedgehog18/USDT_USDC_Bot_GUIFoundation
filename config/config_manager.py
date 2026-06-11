import json
from dataclasses import MISSING, dataclass, fields
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BotConfig:
    symbol: str
    mode: str
    market_data_source: str
    binance_base_url: str

    target_profit: float
    trade_size_percent: float
    max_active_cycles: int

    work_window_minutes: int
    short_window_minutes: int
    long_window_minutes: int

    min_market_activity_score: float
    min_cycle_prediction_score: float
    buy_zone_max: float
    sell_zone_min: float

    min_usdt_reserve_percent: float
    min_usdc_reserve_percent: float

    database_path: str
    use_real_market_data: bool

    price_tick_size: float
    quantity_step_size: float
    min_notional: float
    maker_fee_percent: float
    taker_fee_percent: float
    market_data_cache_ttl_seconds: int
    runner_interval_seconds: int
    max_runner_iterations: int

    order_book_limit: int = 20
    trade_history_limit: int = 50
    volatility_window: int = 30

    max_allowed_spread: float = 0.0002
    min_liquidity_score: float = 5.0
    min_market_health_score: float = 50.0

    log_file_path: str = "logs/bot.log"
    log_level: str = "INFO"

    backtest_interval: str = "1m"
    backtest_limit: int = 500
    backtest_initial_usdt: float = 50.0
    backtest_initial_usdc: float = 50.0

    paper_max_drawdown: float = 0.05
    paper_max_losing_cycles: int = 3
    paper_min_portfolio_value: float = 80.0

    strategy_profile: str = "strict_current"


class ConfigManager:
    DEFAULT_PATH = Path("config/settings.json")

    def __init__(self, path: str | Path | None = None) -> None:
        self.path = Path(path) if path else self.DEFAULT_PATH
        self.config = self.load()

    def load(self) -> BotConfig:
        if not self.path.exists():
            raise FileNotFoundError(f"Файл конфігурації не знайдено: {self.path}")

        data = json.loads(self.path.read_text(encoding="utf-8"))
        self._validate_required_keys(data)

        return BotConfig(
            symbol=str(data["symbol"]),
            mode=str(data["mode"]),
            market_data_source=str(data["market_data_source"]),
            binance_base_url=str(data["binance_base_url"]),
            target_profit=float(data["target_profit"]),
            trade_size_percent=float(data["trade_size_percent"]),
            max_active_cycles=int(data["max_active_cycles"]),
            work_window_minutes=int(data["work_window_minutes"]),
            short_window_minutes=int(data["short_window_minutes"]),
            long_window_minutes=int(data["long_window_minutes"]),
            min_market_activity_score=float(data["min_market_activity_score"]),
            min_cycle_prediction_score=float(data["min_cycle_prediction_score"]),
            buy_zone_max=float(data["buy_zone_max"]),
            sell_zone_min=float(data["sell_zone_min"]),
            min_usdt_reserve_percent=float(data["min_usdt_reserve_percent"]),
            min_usdc_reserve_percent=float(data["min_usdc_reserve_percent"]),
            database_path=str(data["database_path"]),
            use_real_market_data=bool(data["use_real_market_data"]),
            price_tick_size=float(data["price_tick_size"]),
            quantity_step_size=float(data["quantity_step_size"]),
            min_notional=float(data["min_notional"]),
            maker_fee_percent=float(data["maker_fee_percent"]),
            taker_fee_percent=float(data["taker_fee_percent"]),
            market_data_cache_ttl_seconds=int(data["market_data_cache_ttl_seconds"]),
            runner_interval_seconds=int(data["runner_interval_seconds"]),
            max_runner_iterations=int(data["max_runner_iterations"]),
            order_book_limit=int(data.get("order_book_limit", BotConfig.order_book_limit)),
            trade_history_limit=int(data.get("trade_history_limit", BotConfig.trade_history_limit)),
            volatility_window=int(data.get("volatility_window", BotConfig.volatility_window)),
            max_allowed_spread=float(data.get("max_allowed_spread", BotConfig.max_allowed_spread)),
            min_liquidity_score=float(data.get("min_liquidity_score", BotConfig.min_liquidity_score)),
            min_market_health_score=float(data.get("min_market_health_score", BotConfig.min_market_health_score)),
            log_file_path=str(data.get("log_file_path", BotConfig.log_file_path)),
            log_level=str(data.get("log_level", BotConfig.log_level)),
            backtest_interval=str(data.get("backtest_interval", BotConfig.backtest_interval)),
            backtest_limit=int(data.get("backtest_limit", BotConfig.backtest_limit)),
            backtest_initial_usdt=float(data.get("backtest_initial_usdt", BotConfig.backtest_initial_usdt)),
            backtest_initial_usdc=float(data.get("backtest_initial_usdc", BotConfig.backtest_initial_usdc)),
            paper_max_drawdown=float(data.get("paper_max_drawdown", BotConfig.paper_max_drawdown)),
            paper_max_losing_cycles=int(data.get("paper_max_losing_cycles", BotConfig.paper_max_losing_cycles)),
            paper_min_portfolio_value=float(data.get("paper_min_portfolio_value", BotConfig.paper_min_portfolio_value)),
            strategy_profile=str(data.get("strategy_profile", BotConfig.strategy_profile)),
        )

    @staticmethod
    def _validate_required_keys(data: dict[str, Any]) -> None:
        required = {
            field.name
            for field in fields(BotConfig)
            if field.default is MISSING and field.default_factory is MISSING
        }

        missing = sorted(required - set(data.keys()))
        if missing:
            raise ValueError(f"У конфігурації відсутні ключі: {', '.join(missing)}")

    def reload(self) -> BotConfig:
        self.config = self.load()
        return self.config
