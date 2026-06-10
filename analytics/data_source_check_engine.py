from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from config.config_manager import BotConfig
from market.binance_market_data_provider import BinanceMarketDataError, BinanceMarketDataProvider


@dataclass(frozen=True)
class DataSourceCheckReport:
    mode: str
    use_real_market_data: bool
    binance_base_url: str
    symbol: str
    binance_ok: bool
    last_price: float | None
    timestamp: str | None
    source: str
    error_message: str | None = None

    @property
    def backtest_source(self) -> str:
        return "BINANCE"

    @property
    def runner_source(self) -> str:
        return self.source

    @property
    def long_paper_run_source(self) -> str:
        return self.source


class DataSourceCheckEngine:
    """Read-only check of the configured market-data source."""

    def __init__(
        self,
        config: BotConfig,
        provider: BinanceMarketDataProvider | None = None,
    ) -> None:
        self.config = config
        self.provider = provider or BinanceMarketDataProvider(
            base_url=config.binance_base_url,
        )

    def build_report(self) -> DataSourceCheckReport:
        try:
            bid_ask = self.provider.get_bid_ask(self.config.symbol)
            now = datetime.now(timezone.utc).isoformat()
            source = "BINANCE" if self.config.use_real_market_data else "MOCK"

            return DataSourceCheckReport(
                mode=self.config.mode,
                use_real_market_data=self.config.use_real_market_data,
                binance_base_url=self.config.binance_base_url,
                symbol=self.config.symbol,
                binance_ok=True,
                last_price=bid_ask.mid_price,
                timestamp=now,
                source=source,
            )
        except BinanceMarketDataError as exc:
            return self._build_failed_report(str(exc))
        except Exception as exc:
            return self._build_failed_report(f"Unexpected data-source check error: {exc}")

    def _build_failed_report(self, error_message: str) -> DataSourceCheckReport:
        source = "FALLBACK" if self.config.use_real_market_data else "MOCK"

        return DataSourceCheckReport(
            mode=self.config.mode,
            use_real_market_data=self.config.use_real_market_data,
            binance_base_url=self.config.binance_base_url,
            symbol=self.config.symbol,
            binance_ok=False,
            last_price=None,
            timestamp=None,
            source=source,
            error_message=error_message,
        )
