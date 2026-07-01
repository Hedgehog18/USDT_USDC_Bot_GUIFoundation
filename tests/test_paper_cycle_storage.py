from pathlib import Path
from datetime import datetime

import pytest

from paper.models import PaperCycle, PaperCycleStatus, PaperOrderSide
from paper.paper_cycle_manager import PaperCycleManager
from paper.paper_exchange import PaperExchange
from paper.paper_portfolio_manager import PaperPortfolioManager
from storage.database_manager import DatabaseManager


def test_database_saves_paper_cycle(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    portfolio = PaperPortfolioManager(initial_usdt=100.0, initial_usdc=100.0)
    exchange = PaperExchange(test_config, portfolio)
    manager = PaperCycleManager(test_config, exchange)

    cycle = manager.open_cycle("BUY_USDC", 1.0)
    row_id = database.save_paper_cycle(cycle)

    assert row_id > 0
    assert database.count_rows("paper_cycles") == 1


def test_database_tracks_buy_execution_quality(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    portfolio = PaperPortfolioManager(initial_usdt=100.0, initial_usdc=100.0)
    exchange = PaperExchange(test_config, portfolio)
    manager = PaperCycleManager(test_config, exchange)

    cycle = manager.open_cycle("BUY_USDC", 1.0, target_profit=0.0002)
    row_id = database.save_paper_cycle(cycle)

    database.update_paper_cycle_execution_path(
        db_id=row_id,
        direction="BUY_USDC",
        open_price=1.0,
        target_price=1.0002,
        quantity=10.0,
        current_price=1.00015,
    )
    database.update_paper_cycle_execution_path(
        db_id=row_id,
        direction="BUY_USDC",
        open_price=1.0,
        target_price=1.0002,
        quantity=10.0,
        current_price=0.9998,
    )

    row = database.load_recent_paper_cycles(limit=1)[0]

    assert row[12] == 1.00015
    assert row[13] == 0.9998
    assert round(row[14], 8) == 0.0015
    assert round(row[15], 8) == -0.002
    assert round(row[16], 8) == 0.00005
    assert row[17] == 0
    assert row[18] == 0


def test_database_tracks_sell_execution_quality_and_near_target(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    portfolio = PaperPortfolioManager(initial_usdt=100.0, initial_usdc=100.0)
    exchange = PaperExchange(test_config, portfolio)
    manager = PaperCycleManager(test_config, exchange)

    cycle = manager.open_cycle("SELL_USDC", 1.0, target_profit=0.0002)
    row_id = database.save_paper_cycle(cycle)

    database.update_paper_cycle_execution_path(
        db_id=row_id,
        direction="SELL_USDC",
        open_price=1.0,
        target_price=0.9998,
        quantity=10.0,
        current_price=0.999804,
    )
    database.update_paper_cycle_execution_path(
        db_id=row_id,
        direction="SELL_USDC",
        open_price=1.0,
        target_price=0.9998,
        quantity=10.0,
        current_price=1.0001,
    )

    row = database.load_recent_paper_cycles(limit=1)[0]

    assert row[12] == 0.999804
    assert row[13] == 1.0001
    assert round(row[14], 8) == 0.00196
    assert round(row[15], 8) == -0.001
    assert round(row[16], 8) == 0.000004
    assert row[17] == 0
    assert row[18] == 1


def test_database_finalizes_missed_target_then_loss_without_changing_actual_pnl(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    portfolio = PaperPortfolioManager(initial_usdt=100.0, initial_usdc=100.0)
    exchange = PaperExchange(test_config, portfolio)
    manager = PaperCycleManager(test_config, exchange)

    cycle = manager.open_cycle("BUY_USDC", 1.0, target_profit=0.0002)
    row_id = database.save_paper_cycle(cycle, strategy_profile="mean_reversion_hf_micro_v1")
    database.update_paper_cycle_execution_path(
        db_id=row_id,
        direction="BUY_USDC",
        open_price=1.0,
        target_price=1.0002,
        quantity=10.0,
        current_price=1.000196,
    )
    closed = PaperCycle(
        id=row_id,
        direction=PaperOrderSide.BUY_USDC,
        status=PaperCycleStatus.CLOSED,
        open_price=1.0,
        close_price=0.9999,
        quantity=10.0,
        open_fee=0.0,
        close_fee=0.0,
        gross_profit=-0.001,
        net_profit=-0.001,
        opened_at=cycle.opened_at,
        closed_at=datetime.utcnow(),
    )
    closed.close_reason = "max_holding_270s"

    database.save_paper_cycle(closed, strategy_profile="mean_reversion_hf_micro_v1")
    row = database.load_recent_paper_cycles(limit=1)[0]
    stats = database.load_paper_cycle_collection_stats("mean_reversion_hf_micro_v1")

    assert row[10] == -0.001
    assert row[18] == 1
    assert round(row[20], 8) == 0.0003
    assert round(row[21], 8) == 0.00196
    assert round(row[22], 8) == 0.00296
    assert stats["missed_target_count"] == 1
    assert stats["missed_target_then_loss_count"] == 1


def test_database_loads_open_paper_cycle_with_strategy_profile(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    portfolio = PaperPortfolioManager(initial_usdt=100.0, initial_usdc=100.0)
    exchange = PaperExchange(test_config, portfolio)
    manager = PaperCycleManager(test_config, exchange)

    cycle = manager.open_cycle("BUY_USDC", 1.0)
    database.save_paper_cycle(cycle, strategy_profile="mean_reversion_v2")

    rows = database.load_open_paper_cycles(limit=10)

    assert len(rows) == 1
    row_id = cycle.id
    assert rows[0][0] == row_id
    assert rows[0][2] == row_id
    assert rows[0][3] == "mean_reversion_v2"
    assert rows[0][4] == "BUY_USDC"


def test_database_loads_open_paper_cycle_recovery_fields(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    portfolio = PaperPortfolioManager(initial_usdt=100.0, initial_usdc=100.0)
    exchange = PaperExchange(test_config, portfolio)
    manager = PaperCycleManager(test_config, exchange)

    cycle = manager.open_cycle("BUY_USDC", 1.0)
    row_id = database.save_paper_cycle(
        cycle,
        strategy_profile="mean_reversion_v2",
        opened_session_id="session-1",
    )

    rows = database.load_open_paper_cycles_with_recovery(limit=10)

    assert rows[0][0] == row_id
    assert rows[0][15] == "session-1"
    assert rows[0][16] == "ACTIVE"


def test_database_updates_only_matching_open_paper_cycle(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    portfolio = PaperPortfolioManager(initial_usdt=100.0, initial_usdc=100.0)
    exchange = PaperExchange(test_config, portfolio)
    first_manager = PaperCycleManager(test_config, exchange)
    second_manager = PaperCycleManager(test_config, exchange)

    first = first_manager.open_cycle("BUY_USDC", 1.0)
    second = second_manager.open_cycle("SELL_USDC", 1.0005)
    first_db_id = database.save_paper_cycle(first, strategy_profile="mean_reversion_v2")
    second_db_id = database.save_paper_cycle(second, strategy_profile="mean_reversion_v2")

    assert first_db_id != second_db_id
    closed_first = PaperCycle(
        id=first_db_id,
        direction=PaperOrderSide.BUY_USDC,
        status=PaperCycleStatus.CLOSED,
        open_price=first.open_price,
        close_price=first.close_price,
        quantity=first.quantity,
        open_fee=first.open_fee,
        close_fee=0.0,
        gross_profit=0.1,
        net_profit=0.1,
        opened_at=first.opened_at,
        closed_at=first.opened_at,
    )

    database.save_paper_cycle(closed_first, strategy_profile="mean_reversion_v2")
    with database.connect() as conn:
        rows = conn.execute(
            """
            SELECT id, cycle_id, status, net_profit
            FROM paper_cycles
            ORDER BY id ASC
            """
        ).fetchall()

    assert rows == [
        (first_db_id, first_db_id, "CLOSED", 0.1),
        (second_db_id, second_db_id, "OPEN", 0.0),
    ]


def test_database_manually_closes_open_paper_cycle(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    portfolio = PaperPortfolioManager(initial_usdt=100.0, initial_usdc=100.0)
    exchange = PaperExchange(test_config, portfolio)
    first_manager = PaperCycleManager(test_config, exchange)
    second_manager = PaperCycleManager(test_config, exchange)

    first = first_manager.open_cycle("BUY_USDC", 1.0)
    second = second_manager.open_cycle("SELL_USDC", 1.0005)
    first_db_id = database.save_paper_cycle(first, strategy_profile="mean_reversion_v2_small_target")
    second_db_id = database.save_paper_cycle(second, strategy_profile="mean_reversion_v2_small_target")

    updated = database.close_paper_cycle_manually(
        db_id=first_db_id,
        close_price=1.0001,
        close_fee=0.0,
        gross_profit=0.001,
        net_profit=0.001,
        close_reason="stale",
        closed_at="2026-06-14T12:00:00",
    )

    assert updated is True
    with database.connect() as conn:
        rows = conn.execute(
            """
            SELECT id, status, close_price, net_profit, close_reason, closed_at
            FROM paper_cycles
            ORDER BY id ASC
            """
        ).fetchall()

    assert rows[0] == (
        first_db_id,
        "CLOSED_MANUAL",
        pytest.approx(1.0001),
        pytest.approx(0.001),
        "stale",
        "2026-06-14T12:00:00",
    )
    assert rows[1][0] == second_db_id
    assert rows[1][1] == "OPEN"


def test_database_loads_paper_cycle_collection_stats_by_profile(tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    opened_at = datetime.utcnow()

    cycles = [
        PaperCycle(
            id=0,
            direction=PaperOrderSide.BUY_USDC,
            status=PaperCycleStatus.CLOSED,
            open_price=1.0,
            close_price=1.0001,
            quantity=10.0,
            open_fee=0.0,
            close_fee=0.0,
            gross_profit=0.01,
            net_profit=0.01,
            opened_at=opened_at,
            closed_at=opened_at,
        ),
        PaperCycle(
            id=0,
            direction=PaperOrderSide.SELL_USDC,
            status=PaperCycleStatus.CLOSED,
            open_price=1.0,
            close_price=0.9999,
            quantity=10.0,
            open_fee=0.0,
            close_fee=0.0,
            gross_profit=-0.02,
            net_profit=-0.02,
            opened_at=opened_at,
            closed_at=opened_at,
        ),
        PaperCycle(
            id=0,
            direction=PaperOrderSide.BUY_USDC,
            status=PaperCycleStatus.OPEN,
            open_price=1.0,
            close_price=1.0001,
            quantity=10.0,
            open_fee=0.0,
            close_fee=0.0,
            gross_profit=0.0,
            net_profit=0.0,
            opened_at=opened_at,
        ),
    ]
    for cycle in cycles:
        database.save_paper_cycle(cycle, strategy_profile="mean_reversion_v2_small_target")
    database.save_paper_cycle(cycles[0], strategy_profile="other_profile")

    stats = database.load_paper_cycle_collection_stats("mean_reversion_v2_small_target")

    assert stats["closed_cycles"] == 2
    assert stats["open_cycles"] == 1
    assert stats["net_profit"] == pytest.approx(-0.01)
    assert stats["winning_cycles"] == 1
    assert stats["breakeven_cycles"] == 0
    assert stats["losing_cycles"] == 1
    assert stats["average_cycle_pnl"] == pytest.approx(-0.005)
    assert stats["expectancy"] == pytest.approx(-0.005)
    assert stats["profit_factor"] == pytest.approx(0.5)
    assert stats["buy_count"] == 1
    assert stats["sell_count"] == 1
    assert stats["win_rate"] == 0.5


def test_database_loads_new_paper_cycle_collection_stats_after_baseline(tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    opened_at = datetime.utcnow()

    def make_cycle(status: PaperCycleStatus, net_profit: float, close_reason: str | None = None) -> PaperCycle:
        cycle = PaperCycle(
            id=0,
            direction=PaperOrderSide.BUY_USDC,
            status=status,
            open_price=1.0,
            close_price=1.0001,
            quantity=10.0,
            open_fee=0.0,
            close_fee=0.0,
            gross_profit=net_profit,
            net_profit=net_profit,
            opened_at=opened_at,
            closed_at=opened_at if status != PaperCycleStatus.OPEN else None,
        )
        setattr(cycle, "close_reason", close_reason)
        return cycle

    database.save_paper_cycle(make_cycle(PaperCycleStatus.CLOSED, 0.01, "target"), strategy_profile="mean_reversion_hf_micro_v1")
    baseline = database.load_paper_cycle_collection_baseline("mean_reversion_hf_micro_v1")

    database.save_paper_cycle(make_cycle(PaperCycleStatus.CLOSED, 0.02, "target"), strategy_profile="mean_reversion_hf_micro_v1")
    database.save_paper_cycle(make_cycle(PaperCycleStatus.CLOSED, -0.01, "max_holding_270s"), strategy_profile="mean_reversion_hf_micro_v1")
    database.save_paper_cycle(make_cycle(PaperCycleStatus.OPEN, 0.0), strategy_profile="mean_reversion_hf_micro_v1")
    manual_id = database.save_paper_cycle(make_cycle(PaperCycleStatus.OPEN, 0.0), strategy_profile="mean_reversion_hf_micro_v1")
    database.close_paper_cycle_manually(
        db_id=manual_id,
        close_price=0.9999,
        close_fee=0.0,
        gross_profit=-0.03,
        net_profit=-0.03,
        close_reason="stale",
        closed_at=opened_at.isoformat(),
    )
    database.save_paper_cycle(make_cycle(PaperCycleStatus.CLOSED, 9.0, "target"), strategy_profile="other_profile")

    stats = database.load_new_paper_cycle_collection_stats(
        "mean_reversion_hf_micro_v1",
        baseline_max_id=int(baseline["max_cycle_id"]),
    )

    assert stats["closed_cycles"] == 3
    assert stats["automatic_closed"] == 2
    assert stats["manual_closed"] == 1
    assert stats["target_closed"] == 1
    assert stats["timeout_closed"] == 1
    assert stats["timeout_profit"] == 0
    assert stats["timeout_breakeven"] == 0
    assert stats["timeout_loss"] == 1
    assert stats["open_cycles"] == 1
    assert stats["net_profit"] == pytest.approx(-0.02)
    assert stats["winning_cycles"] == 1
    assert stats["breakeven_cycles"] == 0
    assert stats["losing_cycles"] == 2
    assert stats["average_cycle_pnl"] == pytest.approx(-0.02 / 3)
    assert stats["expectancy"] == pytest.approx(-0.02 / 3)
    assert stats["profit_factor"] == pytest.approx(0.02 / 0.04)
    assert stats["buy_count"] == 3
    assert stats["buy_total_pnl"] == pytest.approx(-0.02)
    assert stats["buy_win_rate"] == pytest.approx(1 / 3)
    assert stats["win_rate"] == pytest.approx(1 / 3)


def test_database_saves_hf_paper_cycle_entry_diagnostics(tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    opened_at = datetime.utcnow()
    cycle = PaperCycle(
        id=0,
        direction=PaperOrderSide.BUY_USDC,
        status=PaperCycleStatus.CLOSED,
        open_price=1.0,
        close_price=0.9999,
        quantity=10.0,
        open_fee=0.0,
        close_fee=0.0,
        gross_profit=-0.001,
        net_profit=-0.001,
        opened_at=opened_at,
        closed_at=opened_at,
    )
    setattr(cycle, "close_reason", "max_holding_270s")
    db_id = database.save_paper_cycle(cycle, strategy_profile="mean_reversion_hf_micro_v1")

    row_id = database.save_hf_paper_cycle_entry_diagnostics(
        paper_cycle_id=db_id,
        strategy_profile="mean_reversion_hf_micro_v1",
        current_price=1.0,
        short_center=1.0001,
        previous_price=1.00005,
        last_different_price=1.00005,
        hf_entry_mode="short_center",
        price_buffer_unique_values=2,
        flat_samples_count=0,
        flat_price_buffer=False,
        entry_direction="BUY_USDC",
        entry_reason="mean_reversion_hf_micro_v1: price below short_center",
    )

    with database.connect() as conn:
        row = conn.execute(
            """
            SELECT id, paper_cycle_id, strategy_profile, current_price, short_center,
                   previous_price, last_different_price, hf_entry_mode,
                   price_buffer_unique_values, flat_samples_count, flat_price_buffer,
                   entry_direction, entry_reason
            FROM hf_paper_cycle_entry_diagnostics
            WHERE paper_cycle_id = ?
            """,
            (db_id,),
        ).fetchone()

    assert row[0] == row_id
    assert row[1] == db_id
    assert row[2] == "mean_reversion_hf_micro_v1"
    assert row[3] == pytest.approx(1.0)
    assert row[4] == pytest.approx(1.0001)
    assert row[5] == pytest.approx(1.00005)
    assert row[6] == pytest.approx(1.00005)
    assert row[7] == "short_center"
    assert row[8] == 2
    assert row[9] == 0
    assert row[10] == 0
    assert row[11] == "BUY_USDC"
    assert row[12] == "mean_reversion_hf_micro_v1: price below short_center"
