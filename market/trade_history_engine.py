from dataclasses import dataclass

from market.binance_market_data_provider import RecentTradeData


@dataclass(frozen=True)
class TradeHistoryMetrics:
    buy_volume: float
    sell_volume: float
    trade_count: int
    volume_delta: float
    average_trade_size: float
    micro_trend: str


class TradeHistoryEngine:
    """Аналіз останніх угод.

    У Binance isBuyerMaker=True означає, що покупець був maker,
    тобто агресором був продавець. Для MVP трактуємо це як sell volume.
    """

    def analyze(self, trades: list[RecentTradeData]) -> TradeHistoryMetrics:
        if not trades:
            return TradeHistoryMetrics(
                buy_volume=0.0,
                sell_volume=0.0,
                trade_count=0,
                volume_delta=0.0,
                average_trade_size=0.0,
                micro_trend="UNKNOWN",
            )

        buy_volume = 0.0
        sell_volume = 0.0

        for trade in trades:
            if trade.is_buyer_maker:
                sell_volume += trade.quantity
            else:
                buy_volume += trade.quantity

        total_volume = buy_volume + sell_volume
        volume_delta = 0.0
        if total_volume > 0:
            volume_delta = (buy_volume - sell_volume) / total_volume

        average_trade_size = total_volume / len(trades)

        if volume_delta > 0.20:
            micro_trend = "BUY_DOMINANT"
        elif volume_delta < -0.20:
            micro_trend = "SELL_DOMINANT"
        else:
            micro_trend = "NEUTRAL"

        return TradeHistoryMetrics(
            buy_volume=buy_volume,
            sell_volume=sell_volume,
            trade_count=len(trades),
            volume_delta=volume_delta,
            average_trade_size=average_trade_size,
            micro_trend=micro_trend,
        )
