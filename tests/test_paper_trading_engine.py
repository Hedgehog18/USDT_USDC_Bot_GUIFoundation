from pathlib import Path

from paper.paper_trading_engine import PaperTradingEngine
from storage.database_manager import DatabaseManager


class FakeMarketAnalyzer:
    def __init__(self, price: float = 1.0):
        self.price = price

    def analyze_market(self):
        from datetime import datetime
        from market.models import MarketState

        return MarketState(
            symbol="USDCUSDT",
            price=self.price,
            bid=self.price - 0.00001,
            ask=self.price + 0.00001,
            spread=0.00002,
            work_low=0.9999,
            work_high=1.0001,
            work_center=1.0,
            work_position=50.0,
            short_low=0.9998,
            short_high=1.0002,
            short_center=1.0,
            short_position=50.0,
            long_low=0.9995,
            long_high=1.0005,
            long_center=1.0,
            long_position=50.0,
            center_confidence="HIGH",
            center_alignment="FLAT",
            tick_activity_score=80.0,
            center_crossing_score=80.0,
            mean_reversion_score=80.0,
            spread_stability_score=90.0,
            corridor_quality_score=80.0,
            market_activity_score=80.0,
            market_regime="ACTIVE",
            order_book_imbalance=0.0,
            order_book_pressure="BALANCED",
            trade_volume_delta=0.0,
            micro_trend="NEUTRAL",
            relative_volatility=0.0,
            volatility_regime="NORMAL",
            market_health_score=100.0,
            market_health_status="HEALTHY",
            market_health_reason="test",
            created_at=datetime.utcnow(),
        )


class FakeDecisionEngine:
    def make_decision(self, market_state):
        from datetime import datetime
        from strategy.models import TradeDecision

        return TradeDecision(
            action="WAIT",
            reason="test",
            confidence="LOW",
            cycle_prediction_score=0.0,
            recommended_trade_size=0.0,
            target_profit=0.0002,
            created_at=datetime.utcnow(),
        )


class FakeRiskManager:
    def validate_decision(self, decision, portfolio, current_price=1.0):
        from strategy.models import RiskResult

        return RiskResult(False, "wait", "LOW")


class FakeBot:
    def __init__(self, price: float = 1.0):
        self.market_analyzer = FakeMarketAnalyzer(price=price)
        self.decision_engine = FakeDecisionEngine()
        self.risk_manager = FakeRiskManager()


class FakeCache:
    def __init__(self):
        self.clear_count = 0

    def clear(self):
        self.clear_count += 1


class FakeBotWithCache(FakeBot):
    def __init__(self):
        super().__init__()
        self.market_data_cache = FakeCache()


def test_paper_trading_engine_runs(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    result = PaperTradingEngine(test_config, database, bot=FakeBot()).run(2)

    assert result.iterations == 2
    assert result.opened_cycles == 0
    assert result.final_portfolio.total_value > 0
    assert database.count_rows("paper_safety_events") == 2


def test_paper_trading_engine_force_refresh_clears_market_cache(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    bot = FakeBotWithCache()

    PaperTradingEngine(
        test_config,
        database,
        bot=bot,
        force_refresh_market_data=True,
    ).run(2)

    assert bot.market_data_cache.clear_count == 2


def test_paper_trading_engine_closes_database_open_cycle(test_config, tmp_path: Path):
    from datetime import datetime
    from paper.models import PaperCycle, PaperCycleStatus, PaperOrderSide

    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    open_cycle = PaperCycle(
        id=1,
        direction=PaperOrderSide.SELL_USDC,
        status=PaperCycleStatus.OPEN,
        open_price=1.0010,
        close_price=1.0008,
        quantity=10.0,
        open_fee=0.0,
        close_fee=0.0,
        gross_profit=0.0,
        net_profit=0.0,
        opened_at=datetime.utcnow(),
    )
    row_id = database.save_paper_cycle(open_cycle, strategy_profile="mean_reversion_v2_small_target")
    close_debug_items = []

    result = PaperTradingEngine(
        test_config,
        database,
        bot=FakeBot(price=1.0007),
        close_debug_callback=close_debug_items.append,
    ).run(1)

    with database.connect() as conn:
        row = conn.execute(
            """
            SELECT id, status, close_price, net_profit
            FROM paper_cycles
            WHERE id = ?
            """,
            (row_id,),
        ).fetchone()

    assert result.closed_cycles == 1
    assert row[0] == row_id
    assert row[1] == "CLOSED"
    assert row[2] == 1.0007
    assert row[3] > 0.0
    assert close_debug_items[0]["db_id"] == row_id
    assert close_debug_items[0]["close_condition_met"] is True
    assert close_debug_items[0]["close_attempted"] is True
    assert close_debug_items[0]["close_result"] == "CLOSED"
