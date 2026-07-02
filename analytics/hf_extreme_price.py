from __future__ import annotations


KNOWN_HF_EXTREME_CLOSE_PRICES = (0.99992000,)
HF_EXTREME_PRICE_EPSILON = 0.00000001


def is_extreme_close_price(
    close_price: float,
    *,
    extra_extreme_prices: set[float] | None = None,
) -> bool:
    prices = set(KNOWN_HF_EXTREME_CLOSE_PRICES)
    if extra_extreme_prices:
        prices.update(extra_extreme_prices)
    return any(abs(float(close_price) - price) <= HF_EXTREME_PRICE_EPSILON for price in prices)
