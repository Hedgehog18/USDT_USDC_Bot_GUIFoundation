from dataclasses import dataclass

from market.binance_market_data_provider import OrderBookData


@dataclass(frozen=True)
class OrderBookMetrics:
    bid_volume: float
    ask_volume: float
    imbalance: float
    best_bid: float
    best_ask: float
    spread: float
    liquidity_score: float
    pressure: str


class OrderBookEngine:
    """Аналіз стакану заявок.

    imbalance:
    - > 0: більше bid-ліквідності;
    - < 0: більше ask-ліквідності.
    """

    def analyze(self, order_book: OrderBookData) -> OrderBookMetrics:
        if not order_book.bids or not order_book.asks:
            return OrderBookMetrics(
                bid_volume=0.0,
                ask_volume=0.0,
                imbalance=0.0,
                best_bid=0.0,
                best_ask=0.0,
                spread=0.0,
                liquidity_score=0.0,
                pressure="UNKNOWN",
            )

        bid_volume = sum(qty for _, qty in order_book.bids)
        ask_volume = sum(qty for _, qty in order_book.asks)
        total_volume = bid_volume + ask_volume

        imbalance = 0.0
        if total_volume > 0:
            imbalance = (bid_volume - ask_volume) / total_volume

        best_bid = order_book.bids[0][0]
        best_ask = order_book.asks[0][0]
        spread = best_ask - best_bid

        liquidity_score = min(100.0, total_volume)

        if imbalance > 0.20:
            pressure = "BID_PRESSURE"
        elif imbalance < -0.20:
            pressure = "ASK_PRESSURE"
        else:
            pressure = "BALANCED"

        return OrderBookMetrics(
            bid_volume=bid_volume,
            ask_volume=ask_volume,
            imbalance=imbalance,
            best_bid=best_bid,
            best_ask=best_ask,
            spread=spread,
            liquidity_score=liquidity_score,
            pressure=pressure,
        )
