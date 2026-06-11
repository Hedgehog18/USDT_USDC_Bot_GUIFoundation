from dataclasses import dataclass

from config.config_manager import BotConfig


@dataclass(frozen=True)
class FeeRates:
    maker: float
    taker: float
    source: str
    note: str


class FeeRateProvider:
    """Resolves effective fee rates without mutating config.

    USDCUSDT currently has verified zero maker/taker commission for the user's
    Binance account. Other symbols keep using local config until an authenticated
    Binance commission fetcher is added.
    """

    ZERO_FEE_SYMBOL_OVERRIDES = {"USDCUSDT"}

    def __init__(self, config: BotConfig) -> None:
        self.config = config

    def get_rates(self, symbol: str | None = None) -> FeeRates:
        effective_symbol = (symbol or self.config.symbol).upper()
        if effective_symbol in self.ZERO_FEE_SYMBOL_OVERRIDES:
            return FeeRates(
                maker=0.0,
                taker=0.0,
                source="USDCUSDT verified Binance commission override",
                note="Verified via Binance Spot API GET /api/v3/account/commission on 2026-06-11.",
            )

        return FeeRates(
            maker=self.config.maker_fee_percent,
            taker=self.config.taker_fee_percent,
            source="local config",
            note="Fallback to config/settings.json maker_fee_percent and taker_fee_percent.",
        )
