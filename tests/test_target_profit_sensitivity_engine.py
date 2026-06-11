from datetime import datetime
from pathlib import Path

from analytics.target_profit_sensitivity_engine import TargetProfitSensitivityEngine
from storage.database_manager import DatabaseManager


def _insert_open_cycle(
    database: DatabaseManager,
    *,
    cycle_id: int,
    profile: str,
    direction: str,
    open_price: float,
    quantity: float = 10.0,
) -> None:
    timestamp = datetime.now().isoformat()
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
                timestamp,
                cycle_id,
                profile,
                direction,
                "OPEN",
                open_price,
                open_price,
                quantity,
                0.0,
                0.0,
                0.0,
                0.0,
                timestamp,
                None,
            ),
        )
        conn.commit()


def test_target_profit_sensitivity_counts_would_close_now(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _insert_open_cycle(
        database,
        cycle_id=1,
        profile="mean_reversion_v2",
        direction="BUY_USDC",
        open_price=1.0,
    )

    report = TargetProfitSensitivityEngine(database, test_config).build_report(
        current_price=1.00015,
        profile="mean_reversion_v2",
        target_values=(0.00005, 0.00020),
    )

    low_target, configured_target = report.results
    assert report.fee_rates.maker == 0.0
    assert report.fee_rates.taker == 0.0
    assert low_target.open_cycles_count == 1
    assert low_target.would_close_now_count == 1
    assert configured_target.would_close_now_count == 0
    assert low_target.profitable_now_count == 1


def test_target_profit_sensitivity_filters_profile_and_recommends_target(test_config, tmp_path: Path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _insert_open_cycle(
        database,
        cycle_id=1,
        profile="mean_reversion_v2",
        direction="SELL_USDC",
        open_price=1.0,
    )
    _insert_open_cycle(
        database,
        cycle_id=2,
        profile="mean_reversion_v1",
        direction="BUY_USDC",
        open_price=1.0,
    )

    report = TargetProfitSensitivityEngine(database, test_config).build_report(
        current_price=0.99985,
        profile="mean_reversion_v2",
        target_values=(0.00005, 0.00010, 0.00020),
    )

    assert [item.open_cycles_count for item in report.results] == [1, 1, 1]
    assert [item.would_close_now_count for item in report.results] == [1, 1, 0]
    assert report.recommendation is not None
    assert report.recommendation.target_profit == 0.00010
