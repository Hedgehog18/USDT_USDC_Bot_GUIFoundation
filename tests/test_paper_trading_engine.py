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


def test_paper_trading_engine_applies_tolerance_only_to_tol1_profile(test_config, tmp_path: Path):
    from datetime import datetime
    from paper.models import PaperCycle, PaperCycleStatus, PaperOrderSide

    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    target_price = 1.0006
    near_target = target_price - test_config.price_tick_size

    strict_cycle = PaperCycle(
        id=1,
        direction=PaperOrderSide.BUY_USDC,
        status=PaperCycleStatus.OPEN,
        open_price=1.0000,
        close_price=target_price,
        quantity=10.0,
        open_fee=0.0,
        close_fee=0.0,
        gross_profit=0.0,
        net_profit=0.0,
        opened_at=datetime.utcnow(),
    )
    tol_cycle = PaperCycle(
        id=2,
        direction=PaperOrderSide.BUY_USDC,
        status=PaperCycleStatus.OPEN,
        open_price=1.0000,
        close_price=target_price,
        quantity=10.0,
        open_fee=0.0,
        close_fee=0.0,
        gross_profit=0.0,
        net_profit=0.0,
        opened_at=datetime.utcnow(),
    )
    strict_id = database.save_paper_cycle(strict_cycle, strategy_profile="mean_reversion_v2_small_target")
    tol_id = database.save_paper_cycle(tol_cycle, strategy_profile="mean_reversion_v2_small_target_tol1")
    close_debug_items = []

    result = PaperTradingEngine(
        test_config,
        database,
        bot=FakeBot(price=near_target),
        close_debug_callback=close_debug_items.append,
        strategy_profile="mean_reversion_v2_small_target_tol1",
    ).run(1)

    with database.connect() as conn:
        strict_status = conn.execute("SELECT status FROM paper_cycles WHERE id = ?", (strict_id,)).fetchone()[0]
        tol_status = conn.execute("SELECT status FROM paper_cycles WHERE id = ?", (tol_id,)).fetchone()[0]

    assert result.closed_cycles == 1
    assert strict_status == "OPEN"
    assert tol_status == "CLOSED"
    by_id = {item["db_id"]: item for item in close_debug_items}
    assert by_id[strict_id]["close_condition_met"] is False
    assert by_id[strict_id]["close_tolerance"] == 0.0
    assert by_id[tol_id]["close_condition_met"] is True
    assert by_id[tol_id]["close_tolerance"] == test_config.price_tick_size


def test_paper_trading_engine_applies_epsilon_to_small_target_profile_only(test_config, tmp_path: Path):
    from datetime import datetime
    from paper.models import PaperCycle, PaperCycleStatus, PaperOrderSide

    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    target_price = 1.00122506
    current_price = 1.00122500

    def open_cycle(identifier: int) -> PaperCycle:
        return PaperCycle(
            id=identifier,
            direction=PaperOrderSide.BUY_USDC,
            status=PaperCycleStatus.OPEN,
            open_price=1.0000,
            close_price=target_price,
            quantity=10.0,
            open_fee=0.0,
            close_fee=0.0,
            gross_profit=0.0,
            net_profit=0.0,
            opened_at=datetime.utcnow(),
        )

    strict_id = database.save_paper_cycle(open_cycle(1), strategy_profile="strict_current")
    v2_id = database.save_paper_cycle(open_cycle(2), strategy_profile="mean_reversion_v2")
    small_id = database.save_paper_cycle(open_cycle(3), strategy_profile="mean_reversion_v2_small_target")
    r7_id = database.save_paper_cycle(open_cycle(4), strategy_profile="mean_reversion_v2_small_target_r7")
    max12h_id = database.save_paper_cycle(open_cycle(5), strategy_profile="mean_reversion_v2_small_target_max12h")
    close_debug_items = []

    result = PaperTradingEngine(
        test_config,
        database,
        bot=FakeBot(price=current_price),
        close_debug_callback=close_debug_items.append,
        strategy_profile="mean_reversion_v2_small_target_r7",
    ).run(1)

    with database.connect() as conn:
        strict_status = conn.execute("SELECT status FROM paper_cycles WHERE id = ?", (strict_id,)).fetchone()[0]
        v2_status = conn.execute("SELECT status FROM paper_cycles WHERE id = ?", (v2_id,)).fetchone()[0]
        small_status = conn.execute("SELECT status FROM paper_cycles WHERE id = ?", (small_id,)).fetchone()[0]
        r7_status = conn.execute("SELECT status FROM paper_cycles WHERE id = ?", (r7_id,)).fetchone()[0]
        max12h_status = conn.execute("SELECT status FROM paper_cycles WHERE id = ?", (max12h_id,)).fetchone()[0]

    assert result.closed_cycles == 2
    assert strict_status == "OPEN"
    assert v2_status == "OPEN"
    assert small_status == "CLOSED"
    assert r7_status == "OPEN"
    assert max12h_status == "CLOSED"
    by_id = {item["db_id"]: item for item in close_debug_items}
    assert by_id[strict_id]["close_condition_met"] is False
    assert by_id[strict_id]["close_rounding_digits"] is None
    assert by_id[strict_id]["close_epsilon"] == 0.0
    assert by_id[v2_id]["close_condition_met"] is False
    assert by_id[v2_id]["close_rounding_digits"] is None
    assert by_id[v2_id]["close_epsilon"] == 0.0
    assert by_id[small_id]["close_condition_met"] is True
    assert by_id[small_id]["close_rounding_digits"] is None
    assert by_id[small_id]["close_epsilon"] == 0.00000010
    assert by_id[small_id]["current_price_raw"] == current_price
    assert by_id[small_id]["target_price_raw"] == target_price
    assert by_id[small_id]["effective_buy_close_price"] == current_price + 0.00000010
    assert by_id[small_id]["effective_sell_close_price"] == current_price - 0.00000010
    assert by_id[small_id]["close_rounding_decimals"] is None
    assert by_id[r7_id]["close_condition_met"] is False
    assert by_id[r7_id]["close_rounding_digits"] == 7
    assert by_id[max12h_id]["close_condition_met"] is True
    assert by_id[max12h_id]["close_epsilon"] == 0.00000010
    assert by_id[max12h_id]["max_holding_condition_met"] is False


def test_paper_trading_engine_max12h_profile_closes_by_normal_target(test_config, tmp_path: Path):
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
    row_id = database.save_paper_cycle(open_cycle, strategy_profile="mean_reversion_v2_small_target_max12h")
    close_debug_items = []

    result = PaperTradingEngine(
        test_config,
        database,
        bot=FakeBot(price=1.0007),
        close_debug_callback=close_debug_items.append,
        strategy_profile="mean_reversion_v2_small_target_max12h",
    ).run(1)

    with database.connect() as conn:
        row = conn.execute(
            "SELECT status, close_reason FROM paper_cycles WHERE id = ?",
            (row_id,),
        ).fetchone()

    assert result.closed_cycles == 1
    assert row[0] == "CLOSED"
    assert row[1] is None
    assert close_debug_items[0]["close_condition_met"] is True
    assert close_debug_items[0]["max_holding_condition_met"] is False
    assert close_debug_items[0]["close_result"] == "CLOSED"


def test_paper_trading_engine_max12h_profile_closes_by_max_holding(test_config, tmp_path: Path):
    from datetime import datetime, timedelta
    from paper.models import PaperCycle, PaperCycleStatus, PaperOrderSide

    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    open_cycle = PaperCycle(
        id=1,
        direction=PaperOrderSide.BUY_USDC,
        status=PaperCycleStatus.OPEN,
        open_price=1.0000,
        close_price=1.0010,
        quantity=10.0,
        open_fee=0.0,
        close_fee=0.0,
        gross_profit=0.0,
        net_profit=0.0,
        opened_at=datetime.utcnow() - timedelta(hours=13),
    )
    row_id = database.save_paper_cycle(open_cycle, strategy_profile="mean_reversion_v2_small_target_max12h")
    close_debug_items = []

    result = PaperTradingEngine(
        test_config,
        database,
        bot=FakeBot(price=0.9999),
        close_debug_callback=close_debug_items.append,
        strategy_profile="mean_reversion_v2_small_target_max12h",
    ).run(1)

    with database.connect() as conn:
        row = conn.execute(
            """
            SELECT status, close_reason, close_price, net_profit
            FROM paper_cycles
            WHERE id = ?
            """,
            (row_id,),
        ).fetchone()

    assert result.closed_cycles == 1
    assert row[0] == "CLOSED_MANUAL"
    assert row[1] == "max_holding_12h"
    assert row[2] == 0.9999
    assert row[3] < 0.0
    assert close_debug_items[0]["max_holding_limit_seconds"] == 12 * 60 * 60
    assert close_debug_items[0]["max_holding_condition_met"] is True
    assert close_debug_items[0]["close_condition_met"] is False
    assert close_debug_items[0]["close_result"] == "CLOSED_MANUAL"
    assert close_debug_items[0]["close_reason"] == "max_holding_12h"


def test_paper_trading_engine_base_profiles_do_not_close_by_max_holding(test_config, tmp_path: Path):
    from datetime import datetime, timedelta
    from paper.models import PaperCycle, PaperCycleStatus, PaperOrderSide

    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    def old_cycle(identifier: int) -> PaperCycle:
        return PaperCycle(
            id=identifier,
            direction=PaperOrderSide.BUY_USDC,
            status=PaperCycleStatus.OPEN,
            open_price=1.0000,
            close_price=1.0010,
            quantity=10.0,
            open_fee=0.0,
            close_fee=0.0,
            gross_profit=0.0,
            net_profit=0.0,
            opened_at=datetime.utcnow() - timedelta(hours=13),
        )

    strict_id = database.save_paper_cycle(old_cycle(1), strategy_profile="strict_current")
    small_id = database.save_paper_cycle(old_cycle(2), strategy_profile="mean_reversion_v2_small_target")
    close_debug_items = []

    result = PaperTradingEngine(
        test_config,
        database,
        bot=FakeBot(price=0.9999),
        close_debug_callback=close_debug_items.append,
        strategy_profile="mean_reversion_v2_small_target",
    ).run(1)

    with database.connect() as conn:
        strict_status = conn.execute("SELECT status FROM paper_cycles WHERE id = ?", (strict_id,)).fetchone()[0]
        small_status = conn.execute("SELECT status FROM paper_cycles WHERE id = ?", (small_id,)).fetchone()[0]

    assert result.closed_cycles == 0
    assert strict_status == "OPEN"
    assert small_status == "OPEN"
    by_id = {item["db_id"]: item for item in close_debug_items}
    assert by_id[strict_id]["max_holding_limit_seconds"] is None
    assert by_id[strict_id]["max_holding_condition_met"] is False
    assert by_id[small_id]["max_holding_limit_seconds"] is None
    assert by_id[small_id]["max_holding_condition_met"] is False
