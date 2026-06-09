from dataclasses import dataclass

from config.config_manager import BotConfig, ConfigManager
from market.binance_market_data_provider import BinanceMarketDataError, BinanceMarketDataProvider
from storage.database_manager import DatabaseManager


@dataclass(frozen=True)
class HealthCheckItem:
    name: str
    ok: bool
    message: str


@dataclass(frozen=True)
class HealthCheckReport:
    ok: bool
    items: list[HealthCheckItem]

    @property
    def failed_items(self) -> list[HealthCheckItem]:
        return [item for item in self.items if not item.ok]


class HealthCheck:
    """Стартова перевірка готовності MVP до запуску."""

    def __init__(
        self,
        config: BotConfig | None = None,
        database: DatabaseManager | None = None,
        market_provider: BinanceMarketDataProvider | None = None,
    ) -> None:
        self.config = config
        self.database = database
        self.market_provider = market_provider

    def run(self) -> HealthCheckReport:
        items = [
            self.check_config(),
            self.check_database(),
            self.check_binance_read_only(),
        ]

        return HealthCheckReport(
            ok=all(item.ok for item in items),
            items=items,
        )

    def check_config(self) -> HealthCheckItem:
        try:
            config = self.config or ConfigManager().config

            if config.mode not in {"DEMO", "REAL"}:
                return HealthCheckItem("config", False, f"Невідомий mode: {config.mode}")

            if config.trade_size_percent <= 0 or config.trade_size_percent > 1:
                return HealthCheckItem("config", False, "trade_size_percent має бути в межах 0..1")

            if config.target_profit <= 0:
                return HealthCheckItem("config", False, "target_profit має бути більшим за 0")

            return HealthCheckItem("config", True, "Конфігурація валідна")
        except Exception as exc:
            return HealthCheckItem("config", False, f"Помилка конфігурації: {exc}")

    def check_database(self) -> HealthCheckItem:
        try:
            database = self.database
            if database is None:
                config = self.config or ConfigManager().config
                database = DatabaseManager(config.database_path)

            # Простий запит до гарантованої таблиці.
            database.count_rows("system_events")

            return HealthCheckItem("database", True, "SQLite доступна")
        except Exception as exc:
            return HealthCheckItem("database", False, f"Помилка SQLite: {exc}")

    def check_binance_read_only(self) -> HealthCheckItem:
        try:
            config = self.config or ConfigManager().config

            if not config.use_real_market_data:
                return HealthCheckItem(
                    "binance_read_only",
                    True,
                    "Real market data вимкнено, Binance перевірка пропущена",
                )

            provider = self.market_provider or BinanceMarketDataProvider(
                base_url=config.binance_base_url
            )
            bid_ask = provider.get_bid_ask(config.symbol)

            if bid_ask.bid <= 0 or bid_ask.ask <= 0:
                return HealthCheckItem(
                    "binance_read_only",
                    False,
                    "Binance повернув некоректні bid/ask",
                )

            return HealthCheckItem(
                "binance_read_only",
                True,
                f"Binance read-only доступний: bid={bid_ask.bid}, ask={bid_ask.ask}",
            )
        except BinanceMarketDataError as exc:
            return HealthCheckItem("binance_read_only", False, str(exc))
        except Exception as exc:
            return HealthCheckItem("binance_read_only", False, f"Помилка Binance check: {exc}")
