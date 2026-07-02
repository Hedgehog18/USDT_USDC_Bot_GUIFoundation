import pytest

from storage.database_manager import DatabaseManager
from analytics.hf_profit_audit_engine import HFProfitAuditEngine


def _insert_cycle(
    database: DatabaseManager,
    *,
    db_id: int,
    profile: str = "mean_reversion_hf_micro_v1",
    quantity: float = 10.0,
    open_price: float = 1.0,
    close_price: float = 1.000005,
    net_profit: float = 0.00005,
    status: str = "CLOSED",
    close_reason: str = "target",
) -> None:
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO paper_cycles (
                id, timestamp, cycle_id, strategy_profile, direction, status,
                open_price, close_price, quantity, open_fee, close_fee,
                gross_profit, net_profit, opened_at, closed_at, close_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, ?, ?, ?, ?, ?)
            """,
            (
                db_id,
                f"2026-07-02T12:{db_id:02d}:00",
                db_id,
                profile,
                "BUY_USDC",
                status,
                open_price,
                close_price,
                quantity,
                net_profit,
                net_profit,
                f"2026-07-02T12:{db_id:02d}:00",
                f"2026-07-02T12:{db_id:02d}:10",
                close_reason,
            ),
        )
        conn.commit()


def test_hf_profit_audit_detects_outliers_and_abnormal_cycles(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _insert_cycle(database, db_id=1, net_profit=0.0001)
    _insert_cycle(database, db_id=2, net_profit=0.012, close_price=1.0015)
    _insert_cycle(database, db_id=3, quantity=25.0, net_profit=0.0002)
    _insert_cycle(database, db_id=4, close_price=0.99992000, net_profit=0.0003)

    report = HFProfitAuditEngine(database).build_report("mean_reversion_hf_micro_v1")

    assert report.total_cycles == 4
    assert report.closed_cycles == 4
    assert report.best_cycle is not None
    assert report.best_cycle.db_id == 2
    assert report.total_net_profit == pytest.approx(0.0126)
    assert [cycle.db_id for cycle in report.suspicious_cycles] == [2]
    assert [cycle.db_id for cycle in report.abnormal_quantity_cycles] == [3]
    assert [cycle.db_id for cycle in report.abnormal_distance_cycles] == [2]
    assert [cycle.db_id for cycle in report.fallback_price_cycles] == [4]


def test_hf_profit_audit_since_id_limits_current_run_scope(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _insert_cycle(database, db_id=1, net_profit=0.1)
    _insert_cycle(database, db_id=2, net_profit=0.2)
    _insert_cycle(database, db_id=3, net_profit=-0.05)

    report = HFProfitAuditEngine(database).build_report("mean_reversion_hf_micro_v1", since_id=1)

    assert report.total_cycles == 3
    assert report.current_run_cycles == 2
    assert report.current_run_net_profit == pytest.approx(0.15)
    assert report.latest_100_net_profit == pytest.approx(0.25)


def test_hf_profit_audit_handles_empty_profile(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    report = HFProfitAuditEngine(database).build_report("mean_reversion_hf_micro_v1")

    assert report.total_cycles == 0
    assert report.closed_cycles == 0
    assert report.best_cycle is None
    assert report.top_cycles == []
