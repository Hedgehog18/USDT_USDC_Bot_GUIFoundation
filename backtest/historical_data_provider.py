from dataclasses import dataclass

from market.binance_market_data_provider import BinanceMarketDataProvider


@dataclass(frozen=True)
class HistoricalCandle:
    open_time: int
    open: float
    high: float
    low: float
    close: float
    volume: float


class HistoricalDataProvider:
    """Read-only завантаження історичних klines для backtest."""

    def __init__(self, provider: BinanceMarketDataProvider) -> None:
        self.provider = provider

    def get_candles(self, symbol: str, interval: str, limit: int) -> list[HistoricalCandle]:
        data = self.provider._get(
            "/api/v3/klines",
            {
                "symbol": symbol,
                "interval": interval,
                "limit": limit,
            },
        )

        return [
            HistoricalCandle(
                open_time=int(row[0]),
                open=float(row[1]),
                high=float(row[2]),
                low=float(row[3]),
                close=float(row[4]),
                volume=float(row[5]),
            )
            for row in data
        ]
