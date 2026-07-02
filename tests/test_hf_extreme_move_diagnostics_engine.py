import pytest

from analytics.hf_extreme_move_diagnostics_engine import HFExtremeMoveDiagnosticsEngine
from storage.database_manager import DatabaseManager


def _insert_cycle(
    database: DatabaseManager,
    *,
    db_id: int,
    profile: str = "mean_reversion_hf_micro_v1",
    direction: str = "SELL_USDC",
    open_price: float = 1.0005,
    close_price: float = 1.0004,
    net_profit: float = 0.001,
    close_reason: str = "target",
) -> None:
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO paper_cycles (
                id, timestamp, cycle_id, strategy_profile, direction, status,
                open_price, close_price, quantity, open_fee, close_fee,
                gross_profit, net_profit, opened_at, closed_at, close_reason
            ) VALUES (?, ?, ?, ?, ?, 'CLOSED', ?, ?, 10, 0, 0, ?, ?, ?, ?, ?)
            """,
            (
                db_id,
                f"2026-07-02T12:{db_id:02d}:00",
                db_id,
                profile,
                direction,
                open_price,
                close_price,
                net_profit,
                net_profit,
                f"2026-07-02T12:{db_id:02d}:00",
                f"2026-07-02T12:{db_id:02d}:30",
                close_reason,
            ),
        )
        conn.commit()


def test_hf_extreme_move_detects_extreme_close_and_top_cycle(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _insert_cycle(database, db_id=1, net_profit=0.01, close_price=0.99992000)
    _insert_cycle(database, db_id=2, net_profit=0.001, close_price=1.0004)

    report = HFExtremeMoveDiagnosticsEngine(database).build_report("mean_reversion_hf_micro_v1")

    assert report.total_cycles == 2
    assert report.extreme_cycles_count == 2  # known fallback plus observed max close price
    assert report.top_profit_cycles[0].db_id == 1
    assert report.top_profit_cycles[0].close_price == pytest.approx(0.99992000)
    assert report.top_profit_cycles[0].is_extreme_close_price is True


def test_hf_extreme_move_contribution_and_recommendation(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _insert_cycle(database, db_id=1, net_profit=0.7, close_price=0.99992000)
    _insert_cycle(database, db_id=2, net_profit=0.2, close_price=1.0001)
    _insert_cycle(database, db_id=3, net_profit=0.1, close_price=1.0002)

    report = HFExtremeMoveDiagnosticsEngine(database).build_report("mean_reversion_hf_micro_v1")

    assert report.lifetime_net_profit == pytest.approx(1.0)
    assert report.extreme_net_profit == pytest.approx(0.8)  # fallback + observed max
    assert report.extreme_profit_share == pytest.approx(0.8)
    assert report.net_without_extreme_cycles == pytest.approx(0.2)
    assert report.recommendation == "EXTREME_DEPENDENT"


def test_hf_extreme_move_windows_and_empty_dataset(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    for db_id in range(1, 121):
        _insert_cycle(database, db_id=db_id, net_profit=0.001, close_price=1.0000 + db_id / 1_000_000)

    report = HFExtremeMoveDiagnosticsEngine(database).build_report("mean_reversion_hf_micro_v1")

    latest_100 = next(window for window in report.windows if window.label == "latest_100")
    lifetime = next(window for window in report.windows if window.label == "lifetime")
    assert latest_100.cycles_count == 100
    assert lifetime.cycles_count == 120

    empty = HFExtremeMoveDiagnosticsEngine(database).build_report("missing_profile")
    assert empty.total_cycles == 0
    assert empty.recommendation == "LOW_EXTREME_IMPACT"
    assert empty.top_profit_cycles == []
