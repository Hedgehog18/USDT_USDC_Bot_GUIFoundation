from trading.exchange_rules_engine import ExchangeRulesEngine


def _with_symbol(test_config, symbol: str):
    return test_config.__class__(**{
        **test_config.__dict__,
        "symbol": symbol,
    })


def test_round_price(test_config):
    engine = ExchangeRulesEngine(test_config)
    assert engine.round_price(1.000019) == 1.00001


def test_round_quantity(test_config):
    engine = ExchangeRulesEngine(test_config)
    assert engine.round_quantity(10.123456) == 10.1234


def test_min_notional_allowed(test_config):
    engine = ExchangeRulesEngine(test_config)
    assert engine.is_notional_allowed(5.0) is True
    assert engine.is_notional_allowed(4.99) is False


def test_profitability_after_rounding_allowed_with_large_target(test_config):
    engine = ExchangeRulesEngine(test_config)
    result = engine.check_profitability_after_rounding(
        direction="BUY_USDC",
        open_price=1.0,
        close_price=1.01,
        budget_value=100.0,
    )
    assert result.allowed is True
    assert result.net_profit > 0


def test_profitability_after_rounding_blocks_small_profit(test_config):
    engine = ExchangeRulesEngine(_with_symbol(test_config, "BTCUSDT"))
    result = engine.check_profitability_after_rounding(
        direction="BUY_USDC",
        open_price=1.0,
        close_price=1.00001,
        budget_value=10.0,
    )
    assert result.allowed is False


def test_profitability_after_rounding_uses_zero_fee_override_for_usdcusdt(test_config):
    engine = ExchangeRulesEngine(test_config)
    result = engine.check_profitability_after_rounding(
        direction="BUY_USDC",
        open_price=1.0,
        close_price=1.00001,
        budget_value=10.0,
    )

    assert result.allowed is True
    assert result.estimated_fees == 0.0
    assert result.net_profit == result.gross_profit
