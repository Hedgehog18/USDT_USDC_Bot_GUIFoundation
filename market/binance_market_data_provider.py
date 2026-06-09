from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import requests

from market.market_data_cache import MarketDataCache


@dataclass(frozen=True)
class BidAsk:
    bid: float
    ask: float

    @property
    def mid_price(self) -> float:
        return (self.bid + self.ask) / 2

    @property
    def spread(self) -> float:
        return self.ask - self.bid


@dataclass(frozen=True)
class KlineCloseData:
    closes: list[float]





@dataclass(frozen=True)
class OrderBookData:
    bids: list[tuple[float, float]]
    asks: list[tuple[float, float]]


@dataclass(frozen=True)
class RecentTradeData:
    price: float
    quantity: float
    is_buyer_maker: bool


class BinanceMarketDataError(RuntimeError):
    pass


class BinanceMarketDataProvider:
    """Read-only market data provider РґР»СЏ Binance Spot."""

    def __init__(
        self,
        base_url: str = "https://api.binance.com",
        timeout: int = 10,
        cache: MarketDataCache | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.cache = cache

    def get_bid_ask(self, symbol: str) -> BidAsk:
        cache_key = f"bid_ask:{symbol}"
        cached = self.cache.get(cache_key) if self.cache else None
        if cached is not None:
            return cached

        data = self._get("/api/v3/ticker/bookTicker", {"symbol": symbol})
        result = BidAsk(bid=float(data["bidPrice"]), ask=float(data["askPrice"]))

        if self.cache:
            self.cache.set(cache_key, result)

        return result

    def get_kline_closes(self, symbol: str, interval: str, limit: int) -> KlineCloseData:
        cache_key = f"klines:{symbol}:{interval}:{limit}"
        cached = self.cache.get(cache_key) if self.cache else None
        if cached is not None:
            return cached

        data = self._get(
            "/api/v3/klines",
            {"symbol": symbol, "interval": interval, "limit": limit},
        )
        result = KlineCloseData(closes=[float(row[4]) for row in data])

        if self.cache:
            self.cache.set(cache_key, result)

        return result


    def get_order_book(self, symbol: str, limit: int = 20) -> OrderBookData:
        cache_key = f"order_book:{symbol}:{limit}"
        cached = self.cache.get(cache_key) if self.cache else None
        if cached is not None:
            return cached

        data = self._get("/api/v3/depth", {"symbol": symbol, "limit": limit})
        result = OrderBookData(
            bids=[(float(price), float(qty)) for price, qty in data.get("bids", [])],
            asks=[(float(price), float(qty)) for price, qty in data.get("asks", [])],
        )

        if self.cache:
            self.cache.set(cache_key, result)

        return result

    def get_recent_trades(self, symbol: str, limit: int = 50) -> list[RecentTradeData]:
        cache_key = f"recent_trades:{symbol}:{limit}"
        cached = self.cache.get(cache_key) if self.cache else None
        if cached is not None:
            return cached

        data = self._get("/api/v3/trades", {"symbol": symbol, "limit": limit})
        result = [
            RecentTradeData(
                price=float(row["price"]),
                quantity=float(row["qty"]),
                is_buyer_maker=bool(row["isBuyerMaker"]),
            )
            for row in data
        ]

        if self.cache:
            self.cache.set(cache_key, result)

        return result

    def _get(self, path: str, params: dict[str, Any]) -> Any:
        url = f"{self.base_url}{path}"
        try:
            response = requests.get(url, params=params, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise BinanceMarketDataError(f"РџРѕРјРёР»РєР° Binance market data: {exc}") from exc

        return response.json()
