from datetime import datetime
from pathlib import Path

from analytics.paper_open_cycle_diagnostics_engine import PaperOpenCycleDiagnosticsEngine
from paper.paper_cycle_manager import PaperCycleManager
from paper.paper_exchange import PaperExchange
from paper.paper_portfolio_manager import PaperPortfolioManager
from storage.database_manager import DatabaseManager


def test_paper_open_cycle_diagnostics_explains_cycle_distance(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    portfolio = PaperPortfolioManager(initial_usdt=100.0, initial_usdc=100.0)
    exchange = PaperExchange(test_config, portfolio)
    manager = PaperCycleManager(test_config, exchange)

    buy_cycle = manager.open_cycle("BUY_USDC", 1.0)
    database.save_paper_cycle(buy_cycle, strategy_profile="mean_reversion_v2")

    report = PaperOpenCycleDiagnosticsEngine(database, test_config).build_report(
        current_price=1.0001,
        current_price_source="TEST",
        current_price_timestamp="2026-06-11T00:00:00",
    )

    assert report.current_price_source == "TEST"
    assert report.current_price_timestamp == "2026-06-11T00:00:00"
    assert report.open_cycles_count == 1
    item = report.open_cycles[0]
    assert item.db_id == buy_cycle.id
    assert item.cycle_id == buy_cycle.id
    assert item.profile == "mean_reversion_v2"
    assert item.direction == "BUY_USDC"
    assert item.target_price == buy_cycle.close_price
    assert item.distance_to_target > 0
    assert item.close_condition_met is False
    assert "below target price" in item.reason_not_closed


def test_paper_open_cycle_diagnostics_detects_met_sell_close_condition(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    opened_at = datetime.now().isoformat()
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO paper_cycles (
                timestamp, cycle_id, strategy_profile, direction, status,
                open_price, close_price, quantity, open_fee, close_fee,
                gross_profit, net_profit, opened_at, closed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                opened_at,
                42,
                "mean_reversion_v2",
                "SELL_USDC",
                "OPEN",
                1.0,
                0.9998,
                10.0,
                0.0,
                0.0,
                0.0,
                0.0,
                opened_at,
                None,
            ),
        )
        conn.commit()

    report = PaperOpenCycleDiagnosticsEngine(database, test_config).build_report(
        current_price=0.9997,
        current_price_source="TEST",
        current_price_timestamp="2026-06-11T00:00:00",
    )

    item = report.open_cycles[0]
    assert item.db_id == 1
    assert item.cycle_id == 42
    assert item.direction == "SELL_USDC"
    assert item.close_condition_met is True
    assert item.distance_to_target < 0
    assert "Close condition is met" in item.reason_not_closed
