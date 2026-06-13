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
    assert stats["win_rate"] == 0.5
