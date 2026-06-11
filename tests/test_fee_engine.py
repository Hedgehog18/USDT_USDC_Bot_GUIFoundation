from trading.fee_engine import FeeEngine


def _with_symbol(test_config, symbol: str):
    return test_config.__class__(**{
        **test_config.__dict__,
        "symbol": symbol,
    })


def test_fee_engine_uses_zero_fee_override_for_usdcusdt(test_config):
    engine = FeeEngine(test_config)

    fees = engine.calculate_fees(
        open_notional=100.0,
        close_notional=100.1,
    )

    assert fees.open_fee == 0.0
    assert fees.close_fee == 0.0
    assert fees.total_fee == 0.0


def test_fee_engine_calculates_config_fees_for_other_symbols(test_config):
    engine = FeeEngine(_with_symbol(test_config, "BTCUSDT"))

    fees = engine.calculate_fees(
        open_notional=100.0,
        close_notional=100.1,
    )

    assert fees.open_fee == 0.1
    assert fees.close_fee == 0.1001
    assert round(fees.total_fee, 4) == 0.2001


def test_fee_engine_calculates_buy_profit(test_config):
    engine = FeeEngine(test_config)

    profit = engine.calculate_profit(
        direction="BUY_USDC",
        open_price=1.0,
        close_price=1.01,
        quantity=100.0,
    )

    assert round(profit.gross_profit, 6) == 1.0
    assert profit.net_profit == profit.gross_profit


def test_fee_engine_calculates_sell_profit(test_config):
    engine = FeeEngine(test_config)

    profit = engine.calculate_profit(
        direction="SELL_USDC",
        open_price=1.01,
        close_price=1.0,
        quantity=100.0,
    )

    assert round(profit.gross_profit, 6) == 1.0
    assert profit.net_profit == profit.gross_profit


def test_exchange_rules_uses_fee_engine(test_config):
    from trading.exchange_rules_engine import ExchangeRulesEngine

    engine = ExchangeRulesEngine(test_config)
    result = engine.check_profitability_after_rounding(
        direction="BUY_USDC",
        open_price=1.0,
        close_price=1.01,
        budget_value=100.0,
    )

    assert result.allowed is True
    assert result.estimated_fees == 0.0
    assert result.net_profit == result.gross_profit
