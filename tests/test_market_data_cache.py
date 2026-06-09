from time import sleep

from market.market_data_cache import MarketDataCache


def test_cache_returns_value_before_ttl():
    cache = MarketDataCache(ttl_seconds=5)
    cache.set("a", 123)

    assert cache.get("a") == 123
    assert cache.size() == 1


def test_cache_expires_value_after_ttl():
    cache = MarketDataCache(ttl_seconds=1)
    cache.set("a", 123)

    sleep(1.1)

    assert cache.get("a") is None
    assert cache.size() == 0


def test_cache_clear():
    cache = MarketDataCache(ttl_seconds=5)
    cache.set("a", 123)
    cache.clear()

    assert cache.get("a") is None
    assert cache.size() == 0
