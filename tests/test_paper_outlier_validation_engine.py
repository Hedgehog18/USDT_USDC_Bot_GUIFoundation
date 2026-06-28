import pytest

from analytics.paper_outlier_validation_engine import PaperOutlierValidationEngine
from storage.database_manager import DatabaseManager


def _insert_cycle(
    database: DatabaseManager,
    *,
    profile: str,
    status: str,
    net_profit: float,
    close_reason: str | None,
) -> int:
    with database.connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO paper_cycles (
                timestamp, cycle_id, strategy_profile, direction, status,
                open_price, close_price, quantity, open_fee, close_fee,
                gross_profit, net_profit, opened_at, closed_at, close_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                "2026-06-28T00:00:00",
                1,
                profile,
                "SELL_USDC",
                status,
                1.0,
                0.9999,
                10.0,
                0.0,
                0.0,
                net_profit,
                net_profit,
                "2026-06-28T00:00:00",
                "2026-06-28T00:01:00",
                close_reason,
            ),
        )
        conn.commit()
        return int(cursor.lastrowid)


def test_paper_outlier_validation_marks_outlier_dependent_run(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    profile = "mean_reversion_hf_micro_v1"
    old_id = _insert_cycle(
        database,
        profile=profile,
        status="CLOSED",
        net_profit=1.0,
        close_reason="target",
    )
    _insert_cycle(database, profile=profile, status="CLOSED", net_profit=0.010, close_reason="target")
    _insert_cycle(database, profile=profile, status="CLOSED", net_profit=0.001, close_reason="target")
    _insert_cycle(
        database,
        profile=profile,
        status="CLOSED",
        net_profit=-0.002,
        close_reason="max_holding_270s",
    )
    _insert_cycle(
        database,
        profile=profile,
        status="CLOSED_MANUAL",
        net_profit=0.0,
        close_reason="stale",
    )
    _insert_cycle(database, profile="other_profile", status="CLOSED", net_profit=2.0, close_reason="target")

    summary = PaperOutlierValidationEngine(database).build_summary(
        profile=profile,
        since_id=old_id,
    )

    assert summary.total_cycles == 4
    assert summary.total_net == pytest.approx(0.009)
    assert summary.best_cycle_net == pytest.approx(0.010)
    assert summary.worst_cycle_net == pytest.approx(-0.002)
    assert summary.median_net == pytest.approx(0.0005)
    assert summary.trimmed_net_without_top_1 == pytest.approx(-0.001)
    assert summary.trimmed_net_without_top_3 == pytest.approx(-0.002)
    assert summary.trimmed_net_without_top_5 == pytest.approx(0.0)
    assert summary.winsorized_net_top_1_to_median == pytest.approx(-0.0005)
    assert summary.winsorized_net_top_3_to_median == pytest.approx(-0.0005)
    assert summary.positive_cycles_count == 2
    assert summary.negative_cycles_count == 1
    assert summary.breakeven_cycles_count == 1
    assert summary.target_closed_count == 2
    assert summary.timeout_closed_count == 1
    assert summary.target_net == pytest.approx(0.011)
    assert summary.timeout_net == pytest.approx(-0.002)
    assert summary.net_without_outliers_positive_or_not is False
    assert summary.top1_profit_share == pytest.approx(0.010 / 0.009)
    assert summary.outlier_risk == "OUTLIER_DEPENDENT"
    assert summary.recommendation == "OUTLIER_DEPENDENT"


def test_paper_outlier_validation_marks_robust_distribution(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    profile = "mean_reversion_hf_micro_v1"
    for _index in range(120):
        _insert_cycle(
            database,
            profile=profile,
            status="CLOSED",
            net_profit=0.001,
            close_reason="target",
        )
    for _index in range(20):
        _insert_cycle(
            database,
            profile=profile,
            status="CLOSED",
            net_profit=-0.0005,
            close_reason="max_holding_270s",
        )

    summary = PaperOutlierValidationEngine(database).build_summary(profile=profile)

    assert summary.total_cycles == 140
    assert summary.trimmed_net_without_top_3 > 0.0
    assert summary.top5_profit_share < 0.50
    assert summary.outlier_risk == "LOW"
    assert summary.recommendation == "ROBUST"


def test_paper_outlier_validation_handles_empty_dataset(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    summary = PaperOutlierValidationEngine(database).build_summary(
        profile="mean_reversion_hf_micro_v1",
    )

    assert summary.total_cycles == 0
    assert summary.total_net == 0.0
    assert summary.winsorized_net_top_1_to_median == 0.0
    assert summary.recommendation == "NEEDS_MORE_DATA"
