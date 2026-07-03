from pathlib import Path

from paper.paper_trading_engine import PaperTradingEngine
from storage.database_manager import DatabaseManager


class FakeMarketAnalyzer:
    def __init__(self, price: float = 1.0, short_center: float = 1.0):
        self.price = price
        self.short_center = short_center
        self.last_data_source = "TEST"

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
            short_center=self.short_center,
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


class FakeProfileBot:
    def __init__(self, config, price: float, short_center: float):
        from strategy.profile_decision_engine import StrategyProfileDecisionEngine
        from strategy.risk_manager import RiskManager

        self.market_analyzer = FakeMarketAnalyzer(price=price, short_center=short_center)
        self.decision_engine = StrategyProfileDecisionEngine(config, "mean_reversion_hf_micro_v1")
        self.risk_manager = RiskManager(config)


class FakeSequenceProfileBot:
    def __init__(self, config, prices: list[float]):
        from paper.hf_short_center_provider import HFShortCenterMarketAnalyzer
        from strategy.profile_decision_engine import StrategyProfileDecisionEngine
        from strategy.risk_manager import RiskManager
        from tests.test_hf_short_center_provider import SequenceAnalyzer

        self.market_analyzer = HFShortCenterMarketAnalyzer(SequenceAnalyzer(prices))
        self.decision_engine = StrategyProfileDecisionEngine(config, "mean_reversion_hf_micro_v1")
        self.risk_manager = RiskManager(config)


class FakeExtremeSequenceProfileBot:
    def __init__(self, config, prices: list[float], *, hour: int = 18):
        from paper.extreme_signal_provider import ExtremeSignalMarketAnalyzer
        from strategy.profile_decision_engine import StrategyProfileDecisionEngine
        from strategy.risk_manager import RiskManager
        from tests.test_extreme_signal_provider import ExtremeSequenceAnalyzer

        self.market_analyzer = ExtremeSignalMarketAnalyzer(ExtremeSequenceAnalyzer(prices, hour=hour))
        self.decision_engine = StrategyProfileDecisionEngine(config, "extreme_strategy_v1")
        self.risk_manager = RiskManager(config)


class FakeCache:
    def __init__(self):
        self.clear_count = 0

    def clear(self):
        self.clear_count += 1


class FakeBotWithCache(FakeBot):
    def __init__(self):
        super().__init__()
        self.market_data_cache = FakeCache()


class FakeClock:
    def __init__(self, now: float = 0.0):
        self.now = now

    def __call__(self) -> float:
        return self.now


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
    session_id = "test-session"
    row_id = database.save_paper_cycle(
        open_cycle,
        strategy_profile="mean_reversion_v2_small_target",
        opened_session_id=session_id,
    )
    close_debug_items = []

    result = PaperTradingEngine(
        test_config,
        database,
        bot=FakeBot(price=1.0007),
        close_debug_callback=close_debug_items.append,
        session_id=session_id,
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

    session_id = "test-session"
    strict_id = database.save_paper_cycle(open_cycle(1), strategy_profile="strict_current", opened_session_id=session_id)
    v2_id = database.save_paper_cycle(open_cycle(2), strategy_profile="mean_reversion_v2", opened_session_id=session_id)
    small_id = database.save_paper_cycle(
        open_cycle(3),
        strategy_profile="mean_reversion_v2_small_target",
        opened_session_id=session_id,
    )
    close_debug_items = []

    result = PaperTradingEngine(
        test_config,
        database,
        bot=FakeBot(price=current_price),
        close_debug_callback=close_debug_items.append,
        strategy_profile="mean_reversion_v2_small_target",
        session_id=session_id,
    ).run(1)

    with database.connect() as conn:
        strict_status = conn.execute("SELECT status FROM paper_cycles WHERE id = ?", (strict_id,)).fetchone()[0]
        v2_status = conn.execute("SELECT status FROM paper_cycles WHERE id = ?", (v2_id,)).fetchone()[0]
        small_status = conn.execute("SELECT status FROM paper_cycles WHERE id = ?", (small_id,)).fetchone()[0]

    assert result.closed_cycles == 1
    assert strict_status == "OPEN"
    assert v2_status == "OPEN"
    assert small_status == "CLOSED"
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


def test_paper_trading_engine_hf_profile_opens_buy(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    bot = FakeProfileBot(test_config, price=1.000005, short_center=1.0001)

    result = PaperTradingEngine(
        test_config,
        database,
        bot=bot,
        strategy_profile="mean_reversion_hf_micro_v1",
    ).run(1)

    rows = database.load_open_paper_cycles(limit=10)
    assert result.opened_cycles == 1
    assert rows[0][3] == "mean_reversion_hf_micro_v1"
    assert rows[0][4] == "BUY_USDC"


def test_paper_trading_engine_hf_profile_opens_sell(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    bot = FakeProfileBot(test_config, price=1.000005, short_center=1.0)

    result = PaperTradingEngine(
        test_config,
        database,
        bot=bot,
        strategy_profile="mean_reversion_hf_micro_v1",
    ).run(1)

    rows = database.load_open_paper_cycles(limit=10)
    assert result.opened_cycles == 1
    assert rows[0][3] == "mean_reversion_hf_micro_v1"
    assert rows[0][4] == "SELL_USDC"


def test_paper_trading_engine_hf_profile_does_not_open_second_cycle(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    bot = FakeProfileBot(test_config, price=1.000005, short_center=1.0001)

    result = PaperTradingEngine(
        test_config,
        database,
        bot=bot,
        strategy_profile="mean_reversion_hf_micro_v1",
    ).run(2)

    rows = database.load_open_paper_cycles(limit=10)
    assert result.opened_cycles == 1
    assert len(rows) == 1


def test_paper_trading_engine_hf_profile_waits_for_short_center_samples(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    bot = FakeSequenceProfileBot(test_config, prices=[1.0001] * 19)
    entry_debug_items = []

    result = PaperTradingEngine(
        test_config,
        database,
        bot=bot,
        entry_zone_debug_callback=entry_debug_items.append,
        strategy_profile="mean_reversion_hf_micro_v1",
    ).run(19)

    rows = database.load_open_paper_cycles(limit=10)
    assert result.opened_cycles == 0
    assert rows == []
    assert entry_debug_items[-1]["reason"].endswith("no_short_center")
    assert entry_debug_items[-1]["market_state"].hf_short_center_samples == 19
    assert entry_debug_items[-1]["market_state"].hf_short_center_ready is False


def test_paper_trading_engine_hf_profile_opens_buy_after_short_center_ready(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    bot = FakeSequenceProfileBot(test_config, prices=([1.0001] * 19) + [1.000005])
    entry_debug_items = []

    result = PaperTradingEngine(
        test_config,
        database,
        bot=bot,
        entry_zone_debug_callback=entry_debug_items.append,
        strategy_profile="mean_reversion_hf_micro_v1",
    ).run(20)

    rows = database.load_open_paper_cycles(limit=10)
    assert result.opened_cycles == 1
    assert rows[0][4] == "BUY_USDC"
    assert entry_debug_items[-1]["market_state"].hf_short_center_samples == 20
    assert entry_debug_items[-1]["market_state"].hf_short_center_ready is True


def test_paper_trading_engine_hf_profile_opens_sell_after_short_center_ready(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    bot = FakeSequenceProfileBot(test_config, prices=([1.0001] * 19) + [1.0002])

    result = PaperTradingEngine(
        test_config,
        database,
        bot=bot,
        strategy_profile="mean_reversion_hf_micro_v1",
    ).run(20)

    rows = database.load_open_paper_cycles(limit=10)
    assert result.opened_cycles == 1
    assert rows[0][4] == "SELL_USDC"


def test_paper_trading_engine_hf_profile_waits_when_price_equals_short_center_after_ready(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    bot = FakeSequenceProfileBot(test_config, prices=[1.0001] * 20)

    result = PaperTradingEngine(
        test_config,
        database,
        bot=bot,
        strategy_profile="mean_reversion_hf_micro_v1",
    ).run(20)

    rows = database.load_open_paper_cycles(limit=10)
    assert result.opened_cycles == 0
    assert rows == []


def test_paper_trading_engine_hf_profile_fallback_sells_when_equal_center_after_lower_price(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    bot = FakeSequenceProfileBot(test_config, prices=[1.0000] + ([1.0001] * 19))
    entry_debug_items = []

    result = PaperTradingEngine(
        test_config,
        database,
        bot=bot,
        entry_zone_debug_callback=entry_debug_items.append,
        strategy_profile="mean_reversion_hf_micro_v1",
    ).run(20)

    rows = database.load_open_paper_cycles(limit=10)
    assert result.opened_cycles == 1
    assert rows[0][4] == "SELL_USDC"
    assert "equal_center_last_different_fallback" in entry_debug_items[-1]["reason"]
    assert entry_debug_items[-1]["market_state"].hf_last_different_price == 1.0000


def test_paper_trading_engine_hf_profile_fallback_buys_when_equal_center_after_higher_price(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    bot = FakeSequenceProfileBot(test_config, prices=[1.0002] + ([1.0001] * 19))
    entry_debug_items = []

    PaperTradingEngine(
        test_config,
        database,
        bot=bot,
        entry_zone_debug_callback=entry_debug_items.append,
        strategy_profile="mean_reversion_hf_micro_v1",
    ).run(20)

    assert entry_debug_items[-1]["action"] == "BUY_USDC"
    assert "equal_center_last_different_fallback" in entry_debug_items[-1]["reason"]
    assert entry_debug_items[-1]["market_state"].hf_last_different_price == 1.0002


def test_paper_trading_engine_extreme_profile_opens_only_when_all_signals_true(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    bot = FakeExtremeSequenceProfileBot(test_config, prices=([1.0000] * 5) + [0.999998])
    entry_debug_items = []

    result = PaperTradingEngine(
        test_config,
        database,
        bot=bot,
        entry_zone_debug_callback=entry_debug_items.append,
        strategy_profile="extreme_strategy_v1",
    ).run(6)

    rows = database.load_open_paper_cycles(limit=10)
    assert result.opened_cycles == 1
    assert len(rows) == 1
    assert rows[0][3] == "extreme_strategy_v1"
    assert rows[0][4] == "SELL_USDC"
    assert entry_debug_items[-1]["market_state"].extreme_signal_detected is True


def test_paper_trading_engine_extreme_profile_waits_without_session_signal(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    bot = FakeExtremeSequenceProfileBot(test_config, prices=([1.0000] * 5) + [0.999998], hour=3)

    result = PaperTradingEngine(
        test_config,
        database,
        bot=bot,
        strategy_profile="extreme_strategy_v1",
    ).run(6)

    assert result.opened_cycles == 0
    assert database.load_open_paper_cycles(limit=10) == []


def test_paper_trading_engine_extreme_profile_waits_without_velocity_spike(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    bot = FakeExtremeSequenceProfileBot(test_config, prices=[1.0000] * 6)

    result = PaperTradingEngine(
        test_config,
        database,
        bot=bot,
        strategy_profile="extreme_strategy_v1",
    ).run(6)

    assert result.opened_cycles == 0


def test_paper_trading_engine_extreme_profile_waits_without_compression(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    bot = FakeExtremeSequenceProfileBot(
        test_config,
        prices=[1.0000, 1.0001, 1.0002, 1.0003, 1.0004, 1.000398],
    )

    result = PaperTradingEngine(
        test_config,
        database,
        bot=bot,
        strategy_profile="extreme_strategy_v1",
    ).run(6)

    assert result.opened_cycles == 0


def test_paper_trading_engine_extreme_profile_does_not_open_second_cycle(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    bot = FakeExtremeSequenceProfileBot(test_config, prices=([1.0000] * 5) + [0.999998] + [0.999996])

    result = PaperTradingEngine(
        test_config,
        database,
        bot=bot,
        strategy_profile="extreme_strategy_v1",
    ).run(7)

    rows = database.load_open_paper_cycles(limit=10)
    assert result.opened_cycles == 1
    assert len(rows) == 1


def test_paper_trading_engine_hf_profile_closes_buy_on_target(test_config, tmp_path: Path):
    from datetime import datetime
    from paper.models import PaperCycle, PaperCycleStatus, PaperOrderSide

    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    open_cycle = PaperCycle(
        id=1,
        direction=PaperOrderSide.BUY_USDC,
        status=PaperCycleStatus.OPEN,
        open_price=1.000005,
        close_price=1.000010,
        quantity=10.0,
        open_fee=0.0,
        close_fee=0.0,
        gross_profit=0.0,
        net_profit=0.0,
        opened_at=datetime.utcnow(),
    )
    session_id = "test-session"
    row_id = database.save_paper_cycle(
        open_cycle,
        strategy_profile="mean_reversion_hf_micro_v1",
        opened_session_id=session_id,
    )
    close_debug_items = []

    result = PaperTradingEngine(
        test_config,
        database,
        bot=FakeBot(price=1.00002),
        close_debug_callback=close_debug_items.append,
        strategy_profile="mean_reversion_hf_micro_v1",
        session_id=session_id,
    ).run(1)

    with database.connect() as conn:
        row = conn.execute("SELECT status, close_reason FROM paper_cycles WHERE id = ?", (row_id,)).fetchone()

    assert result.closed_cycles == 1
    assert row == ("CLOSED", "target")
    assert close_debug_items[0]["target_close_condition_met"] is True
    assert close_debug_items[0]["close_reason"] == "target"


def test_paper_trading_engine_hf_profile_closes_sell_on_target(test_config, tmp_path: Path):
    from datetime import datetime
    from paper.models import PaperCycle, PaperCycleStatus, PaperOrderSide

    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    open_cycle = PaperCycle(
        id=1,
        direction=PaperOrderSide.SELL_USDC,
        status=PaperCycleStatus.OPEN,
        open_price=1.000005,
        close_price=1.000000,
        quantity=10.0,
        open_fee=0.0,
        close_fee=0.0,
        gross_profit=0.0,
        net_profit=0.0,
        opened_at=datetime.utcnow(),
    )
    session_id = "test-session"
    row_id = database.save_paper_cycle(
        open_cycle,
        strategy_profile="mean_reversion_hf_micro_v1",
        opened_session_id=session_id,
    )

    result = PaperTradingEngine(
        test_config,
        database,
        bot=FakeBot(price=0.99999),
        strategy_profile="mean_reversion_hf_micro_v1",
        session_id=session_id,
    ).run(1)

    with database.connect() as conn:
        row = conn.execute("SELECT status, close_reason FROM paper_cycles WHERE id = ?", (row_id,)).fetchone()

    assert result.closed_cycles == 1
    assert row == ("CLOSED", "target")


def test_paper_trading_engine_extreme_profile_closes_sell_on_target(test_config, tmp_path: Path):
    from datetime import datetime
    from paper.models import PaperCycle, PaperCycleStatus, PaperOrderSide

    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    open_cycle = PaperCycle(
        id=1,
        direction=PaperOrderSide.SELL_USDC,
        status=PaperCycleStatus.OPEN,
        open_price=1.000005,
        close_price=1.000000,
        quantity=10.0,
        open_fee=0.0,
        close_fee=0.0,
        gross_profit=0.0,
        net_profit=0.0,
        opened_at=datetime.utcnow(),
    )
    session_id = "test-session"
    row_id = database.save_paper_cycle(
        open_cycle,
        strategy_profile="extreme_strategy_v1",
        opened_session_id=session_id,
    )
    close_debug_items = []

    result = PaperTradingEngine(
        test_config,
        database,
        bot=FakeBot(price=0.99999),
        close_debug_callback=close_debug_items.append,
        strategy_profile="extreme_strategy_v1",
        session_id=session_id,
    ).run(1)

    with database.connect() as conn:
        row = conn.execute("SELECT status, close_reason FROM paper_cycles WHERE id = ?", (row_id,)).fetchone()

    assert result.closed_cycles == 1
    assert row == ("CLOSED", "extreme_target")
    assert close_debug_items[0]["close_reason"] == "extreme_target"


def test_paper_trading_engine_extreme_profile_closes_after_timeout(test_config, tmp_path: Path):
    from datetime import datetime
    from paper.models import PaperCycle, PaperCycleStatus, PaperOrderSide

    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    open_cycle = PaperCycle(
        id=1,
        direction=PaperOrderSide.SELL_USDC,
        status=PaperCycleStatus.OPEN,
        open_price=1.000005,
        close_price=0.999500,
        quantity=10.0,
        open_fee=0.0,
        close_fee=0.0,
        gross_profit=0.0,
        net_profit=0.0,
        opened_at=datetime.utcnow(),
    )
    session_id = "test-session"
    row_id = database.save_paper_cycle(
        open_cycle,
        strategy_profile="extreme_strategy_v1",
        opened_session_id=session_id,
    )
    close_debug_items = []
    tracking_started = {row_id: 0.0}
    clock = FakeClock(61.0)

    result = PaperTradingEngine(
        test_config,
        database,
        bot=FakeBot(price=1.000000),
        close_debug_callback=close_debug_items.append,
        strategy_profile="extreme_strategy_v1",
        session_id=session_id,
        cycle_tracking_started_at_by_db_id=tracking_started,
        monotonic_clock=clock,
    ).run(1)

    with database.connect() as conn:
        row = conn.execute("SELECT status, close_reason FROM paper_cycles WHERE id = ?", (row_id,)).fetchone()

    assert result.closed_cycles == 1
    assert row == ("CLOSED", "extreme_timeout")
    assert close_debug_items[0]["max_holding_limit"] == 60.0
    assert close_debug_items[0]["max_holding_condition_met"] is True


def test_paper_trading_engine_hf_profile_closes_after_270s_timeout(test_config, tmp_path: Path):
    from datetime import datetime
    from paper.models import PaperCycle, PaperCycleStatus, PaperOrderSide

    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    open_cycle = PaperCycle(
        id=1,
        direction=PaperOrderSide.BUY_USDC,
        status=PaperCycleStatus.OPEN,
        open_price=1.000005,
        close_price=1.000500,
        quantity=10.0,
        open_fee=0.0,
        close_fee=0.0,
        gross_profit=0.0,
        net_profit=0.0,
        opened_at=datetime.utcnow(),
    )
    session_id = "test-session"
    row_id = database.save_paper_cycle(
        open_cycle,
        strategy_profile="mean_reversion_hf_micro_v1",
        opened_session_id=session_id,
    )
    close_debug_items = []
    tracking_started = {row_id: 0.0}
    clock = FakeClock(271.0)

    result = PaperTradingEngine(
        test_config,
        database,
        bot=FakeBot(price=1.000000),
        close_debug_callback=close_debug_items.append,
        strategy_profile="mean_reversion_hf_micro_v1",
        session_id=session_id,
        cycle_tracking_started_at_by_db_id=tracking_started,
        monotonic_clock=clock,
    ).run(1)

    with database.connect() as conn:
        row = conn.execute("SELECT status, close_reason FROM paper_cycles WHERE id = ?", (row_id,)).fetchone()

    assert result.closed_cycles == 1
    assert row == ("CLOSED", "max_holding_270s")
    assert close_debug_items[0]["target_close_condition_met"] is False
    assert close_debug_items[0]["max_holding_condition_met"] is True
    assert close_debug_items[0]["max_holding_limit"] == 270.0
    assert close_debug_items[0]["close_reason"] == "max_holding_270s"


def test_paper_trading_engine_hf_profile_does_not_timeout_before_270s(test_config, tmp_path: Path):
    from datetime import datetime
    from paper.models import PaperCycle, PaperCycleStatus, PaperOrderSide

    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    open_cycle = PaperCycle(
        id=1,
        direction=PaperOrderSide.BUY_USDC,
        status=PaperCycleStatus.OPEN,
        open_price=1.000005,
        close_price=1.000500,
        quantity=10.0,
        open_fee=0.0,
        close_fee=0.0,
        gross_profit=0.0,
        net_profit=0.0,
        opened_at=datetime.utcnow(),
    )
    session_id = "test-session"
    row_id = database.save_paper_cycle(
        open_cycle,
        strategy_profile="mean_reversion_hf_micro_v1",
        opened_session_id=session_id,
    )
    close_debug_items = []
    tracking_started = {row_id: 0.0}
    clock = FakeClock(269.0)

    result = PaperTradingEngine(
        test_config,
        database,
        bot=FakeBot(price=1.000000),
        close_debug_callback=close_debug_items.append,
        strategy_profile="mean_reversion_hf_micro_v1",
        session_id=session_id,
        cycle_tracking_started_at_by_db_id=tracking_started,
        monotonic_clock=clock,
    ).run(1)

    with database.connect() as conn:
        row = conn.execute("SELECT status, close_reason FROM paper_cycles WHERE id = ?", (row_id,)).fetchone()

    assert result.closed_cycles == 0
    assert row == ("OPEN", None)
    assert close_debug_items[0]["target_close_condition_met"] is False
    assert close_debug_items[0]["max_holding_condition_met"] is False
    assert close_debug_items[0]["close_reason"] is None


def test_paper_trading_engine_newly_observed_cycle_tracking_starts_near_zero(test_config, tmp_path: Path):
    from datetime import datetime, timedelta
    from paper.models import PaperCycle, PaperCycleStatus, PaperOrderSide

    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    open_cycle = PaperCycle(
        id=1,
        direction=PaperOrderSide.BUY_USDC,
        status=PaperCycleStatus.OPEN,
        open_price=1.000005,
        close_price=1.000500,
        quantity=10.0,
        open_fee=0.0,
        close_fee=0.0,
        gross_profit=0.0,
        net_profit=0.0,
        opened_at=datetime.utcnow() - timedelta(minutes=180),
    )
    session_id = "test-session"
    row_id = database.save_paper_cycle(
        open_cycle,
        strategy_profile="mean_reversion_hf_micro_v1",
        opened_session_id=session_id,
    )
    close_debug_items = []
    tracking_started: dict[int, float] = {}
    clock = FakeClock(1000.0)

    result = PaperTradingEngine(
        test_config,
        database,
        bot=FakeBot(price=1.000000),
        close_debug_callback=close_debug_items.append,
        strategy_profile="mean_reversion_hf_micro_v1",
        session_id=session_id,
        cycle_tracking_started_at_by_db_id=tracking_started,
        monotonic_clock=clock,
    ).run(1)

    with database.connect() as conn:
        row = conn.execute("SELECT status, close_reason FROM paper_cycles WHERE id = ?", (row_id,)).fetchone()

    assert result.closed_cycles == 0
    assert row == ("OPEN", None)
    assert tracking_started[row_id] == 1000.0
    assert close_debug_items[0]["cycle_age"] < 2.0
    assert close_debug_items[0]["max_holding_condition_met"] is False


def test_paper_trading_engine_runtime_tracking_reaches_one_minute(test_config, tmp_path: Path):
    from datetime import datetime
    from paper.models import PaperCycle, PaperCycleStatus, PaperOrderSide

    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    open_cycle = PaperCycle(
        id=1,
        direction=PaperOrderSide.BUY_USDC,
        status=PaperCycleStatus.OPEN,
        open_price=1.000005,
        close_price=1.000500,
        quantity=10.0,
        open_fee=0.0,
        close_fee=0.0,
        gross_profit=0.0,
        net_profit=0.0,
        opened_at=datetime.utcnow(),
    )
    session_id = "test-session"
    row_id = database.save_paper_cycle(
        open_cycle,
        strategy_profile="mean_reversion_hf_micro_v1",
        opened_session_id=session_id,
    )
    close_debug_items = []
    tracking_started = {row_id: 10.0}
    clock = FakeClock(70.0)

    PaperTradingEngine(
        test_config,
        database,
        bot=FakeBot(price=1.000000),
        close_debug_callback=close_debug_items.append,
        strategy_profile="mean_reversion_hf_micro_v1",
        session_id=session_id,
        cycle_tracking_started_at_by_db_id=tracking_started,
        monotonic_clock=clock,
    ).run(1)

    assert close_debug_items[0]["cycle_age"] == 60.0
    assert close_debug_items[0]["max_holding_condition_met"] is False


def test_paper_trading_engine_hf_timeout_ignores_missing_short_center(test_config, tmp_path: Path):
    from datetime import datetime
    from paper.models import PaperCycle, PaperCycleStatus, PaperOrderSide

    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    open_cycle = PaperCycle(
        id=1,
        direction=PaperOrderSide.SELL_USDC,
        status=PaperCycleStatus.OPEN,
        open_price=1.000005,
        close_price=0.999500,
        quantity=10.0,
        open_fee=0.0,
        close_fee=0.0,
        gross_profit=0.0,
        net_profit=0.0,
        opened_at=datetime.utcnow(),
    )
    session_id = "test-session"
    row_id = database.save_paper_cycle(
        open_cycle,
        strategy_profile="mean_reversion_hf_micro_v1",
        opened_session_id=session_id,
    )
    close_debug_items = []
    tracking_started = {row_id: 0.0}
    clock = FakeClock(271.0)

    result = PaperTradingEngine(
        test_config,
        database,
        bot=FakeProfileBot(test_config, price=1.000000, short_center=0.0),
        close_debug_callback=close_debug_items.append,
        strategy_profile="mean_reversion_hf_micro_v1",
        session_id=session_id,
        cycle_tracking_started_at_by_db_id=tracking_started,
        monotonic_clock=clock,
    ).run(1)

    with database.connect() as conn:
        row = conn.execute("SELECT status, close_reason FROM paper_cycles WHERE id = ?", (row_id,)).fetchone()

    assert result.closed_cycles == 1
    assert row == ("CLOSED", "max_holding_270s")
    assert close_debug_items[0]["max_holding_condition_met"] is True
    assert close_debug_items[0]["close_reason"] == "max_holding_270s"


def test_paper_trading_engine_hf_timeout_ignores_no_signal_entry_result(test_config, tmp_path: Path):
    from datetime import datetime
    from paper.models import PaperCycle, PaperCycleStatus, PaperOrderSide

    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    open_cycle = PaperCycle(
        id=1,
        direction=PaperOrderSide.BUY_USDC,
        status=PaperCycleStatus.OPEN,
        open_price=1.000005,
        close_price=1.000500,
        quantity=10.0,
        open_fee=0.0,
        close_fee=0.0,
        gross_profit=0.0,
        net_profit=0.0,
        opened_at=datetime.utcnow(),
    )
    session_id = "test-session"
    row_id = database.save_paper_cycle(
        open_cycle,
        strategy_profile="mean_reversion_hf_micro_v1",
        opened_session_id=session_id,
    )
    entry_debug_items = []
    tracking_started = {row_id: 0.0}
    clock = FakeClock(271.0)

    result = PaperTradingEngine(
        test_config,
        database,
        bot=FakeBot(price=1.000000),
        entry_zone_debug_callback=entry_debug_items.append,
        strategy_profile="mean_reversion_hf_micro_v1",
        session_id=session_id,
        cycle_tracking_started_at_by_db_id=tracking_started,
        monotonic_clock=clock,
    ).run(1)

    with database.connect() as conn:
        row = conn.execute("SELECT status, close_reason FROM paper_cycles WHERE id = ?", (row_id,)).fetchone()

    assert result.closed_cycles == 1
    assert row == ("CLOSED", "max_holding_270s")
    assert entry_debug_items == []


def test_paper_trading_engine_requires_recovery_for_previous_session_open_cycle(test_config, tmp_path: Path):
    from datetime import datetime
    from paper.models import PaperCycle, PaperCycleStatus, PaperOrderSide

    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    open_cycle = PaperCycle(
        id=1,
        direction=PaperOrderSide.BUY_USDC,
        status=PaperCycleStatus.OPEN,
        open_price=1.0000,
        close_price=1.0001,
        quantity=10.0,
        open_fee=0.0,
        close_fee=0.0,
        gross_profit=0.0,
        net_profit=0.0,
        opened_at=datetime.utcnow(),
    )
    row_id = database.save_paper_cycle(
        open_cycle,
        strategy_profile="mean_reversion_v2_small_target",
        opened_session_id="old-session",
    )
    close_debug_items = []

    result = PaperTradingEngine(
        test_config,
        database,
        bot=FakeBot(price=1.0002),
        close_debug_callback=close_debug_items.append,
        session_id="new-session",
    ).run(1)

    with database.connect() as conn:
        row = conn.execute(
            "SELECT status, recovery_status, close_price FROM paper_cycles WHERE id = ?",
            (row_id,),
        ).fetchone()

    assert result.recovery_required is True
    assert result.closed_cycles == 0
    assert row == ("OPEN", "RECOVERY_REQUIRED", 1.0001)
    assert close_debug_items[0]["close_result"] == "RECOVERY_REQUIRED"
    assert close_debug_items[0]["close_attempted"] is False


def test_paper_trading_engine_does_not_timeout_previous_session_open_cycle(test_config, tmp_path: Path):
    from datetime import datetime, timedelta
    from paper.models import PaperCycle, PaperCycleStatus, PaperOrderSide

    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    open_cycle = PaperCycle(
        id=1,
        direction=PaperOrderSide.BUY_USDC,
        status=PaperCycleStatus.OPEN,
        open_price=1.000005,
        close_price=1.000500,
        quantity=10.0,
        open_fee=0.0,
        close_fee=0.0,
        gross_profit=0.0,
        net_profit=0.0,
        opened_at=datetime.utcnow() - timedelta(hours=2),
    )
    row_id = database.save_paper_cycle(
        open_cycle,
        strategy_profile="mean_reversion_hf_micro_v1",
        opened_session_id="old-session",
    )
    close_debug_items = []

    result = PaperTradingEngine(
        test_config,
        database,
        bot=FakeBot(price=1.000000),
        close_debug_callback=close_debug_items.append,
        strategy_profile="mean_reversion_hf_micro_v1",
        session_id="new-session",
    ).run(1)

    with database.connect() as conn:
        row = conn.execute(
            "SELECT status, close_reason, recovery_status FROM paper_cycles WHERE id = ?",
            (row_id,),
        ).fetchone()

    assert result.recovery_required is True
    assert result.closed_cycles == 0
    assert row == ("OPEN", None, "RECOVERY_REQUIRED")
    assert close_debug_items[0]["max_holding_condition_met"] is False


def test_paper_trading_engine_recovery_blocks_new_entries(test_config, tmp_path: Path):
    from datetime import datetime
    from paper.models import PaperCycle, PaperCycleStatus, PaperOrderSide

    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    open_cycle = PaperCycle(
        id=1,
        direction=PaperOrderSide.SELL_USDC,
        status=PaperCycleStatus.OPEN,
        open_price=1.0002,
        close_price=1.0001,
        quantity=10.0,
        open_fee=0.0,
        close_fee=0.0,
        gross_profit=0.0,
        net_profit=0.0,
        opened_at=datetime.utcnow(),
    )
    database.save_paper_cycle(
        open_cycle,
        strategy_profile="mean_reversion_hf_micro_v1",
        opened_session_id="old-session",
    )

    result = PaperTradingEngine(
        test_config,
        database,
        bot=FakeProfileBot(test_config, price=1.000005, short_center=1.0001),
        strategy_profile="mean_reversion_hf_micro_v1",
        session_id="new-session",
    ).run(2)

    rows = database.load_open_paper_cycles(limit=10)
    assert result.recovery_required is True
    assert result.opened_cycles == 0
    assert len(rows) == 1


def test_paper_trading_engine_safe_stop_blocks_new_entries(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    result = PaperTradingEngine(
        test_config,
        database,
        bot=FakeProfileBot(test_config, price=1.000005, short_center=1.0001),
        strategy_profile="mean_reversion_hf_micro_v1",
        safe_stop=True,
    ).run(1)

    assert result.shutdown_requested is True
    assert result.opened_cycles == 0
    assert database.load_open_paper_cycles(limit=10) == []


def test_paper_trading_engine_safe_stop_closes_current_session_cycle_then_exits(test_config, tmp_path: Path):
    from datetime import datetime
    from paper.models import PaperCycle, PaperCycleStatus, PaperOrderSide

    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    session_id = "test-session"
    open_cycle = PaperCycle(
        id=1,
        direction=PaperOrderSide.BUY_USDC,
        status=PaperCycleStatus.OPEN,
        open_price=1.0000,
        close_price=1.0001,
        quantity=10.0,
        open_fee=0.0,
        close_fee=0.0,
        gross_profit=0.0,
        net_profit=0.0,
        opened_at=datetime.utcnow(),
    )
    row_id = database.save_paper_cycle(
        open_cycle,
        strategy_profile="mean_reversion_v2_small_target",
        opened_session_id=session_id,
    )

    result = PaperTradingEngine(
        test_config,
        database,
        bot=FakeProfileBot(test_config, price=1.0002, short_center=1.0001),
        strategy_profile="mean_reversion_v2_small_target",
        session_id=session_id,
        safe_stop=True,
    ).run(3)

    with database.connect() as conn:
        status = conn.execute("SELECT status FROM paper_cycles WHERE id = ?", (row_id,)).fetchone()[0]

    assert result.shutdown_requested is True
    assert result.closed_cycles == 1
    assert result.opened_cycles == 0
    assert status == "CLOSED"
