import pytest

from analytics.paper_profit_concentration_engine import PaperProfitConcentrationEngine
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
                "BUY_USDC",
                status,
                1.0,
                1.0001,
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


def test_paper_profit_concentration_counts_top_share_and_net_without_best(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    profile = "mean_reversion_hf_micro_v1"
    old_id = _insert_cycle(
        database,
        profile=profile,
        status="CLOSED",
        net_profit=0.500,
        close_reason="target",
    )
    _insert_cycle(database, profile=profile, status="CLOSED", net_profit=0.004, close_reason="target")
    _insert_cycle(database, profile=profile, status="CLOSED", net_profit=0.003, close_reason="target")
    _insert_cycle(
        database,
        profile=profile,
        status="CLOSED",
        net_profit=0.002,
        close_reason="max_holding_270s",
    )
    _insert_cycle(
        database,
        profile=profile,
        status="CLOSED",
        net_profit=0.001,
        close_reason="max_holding_270s",
    )
    _insert_cycle(
        database,
        profile=profile,
        status="CLOSED",
        net_profit=-0.001,
        close_reason="max_holding_270s",
    )
    _insert_cycle(
        database,
        profile=profile,
        status="CLOSED_MANUAL",
        net_profit=0.0,
        close_reason="stale",
    )
    _insert_cycle(database, profile="other_profile", status="CLOSED", net_profit=1.0, close_reason="target")

    summary = PaperProfitConcentrationEngine(database).build_summary(
        profile=profile,
        since_id=old_id,
    )

    assert summary.realized_cycles_count == 6
    assert summary.total_net_profit == pytest.approx(0.009)
    assert summary.best_cycle_net == pytest.approx(0.004)
    assert summary.worst_cycle_net == pytest.approx(-0.001)
    assert summary.net_without_best_1 == pytest.approx(0.005)
    assert summary.net_without_best_3 == pytest.approx(0.0)
    assert summary.net_without_best_5 == pytest.approx(-0.001)
    assert summary.top1_profit_share == pytest.approx(0.004 / 0.009)
    assert summary.top3_profit_share == pytest.approx(0.009 / 0.009)
    assert summary.top5_profit_share == pytest.approx(0.010 / 0.009)
    assert summary.positive_cycles_count == 4
    assert summary.negative_cycles_count == 1
    assert summary.breakeven_cycles_count == 1
    assert summary.positive_net_total == pytest.approx(0.010)
    assert summary.negative_net_total == pytest.approx(-0.001)
    assert summary.average_positive_cycle == pytest.approx(0.0025)
    assert summary.average_negative_cycle == pytest.approx(-0.001)
    assert summary.median_net == pytest.approx(0.0015)
    assert summary.target_closed_net == pytest.approx(0.007)
    assert summary.timeout_closed_net == pytest.approx(0.002)
    assert summary.target_closed_count == 2
    assert summary.timeout_closed_count == 3
    assert summary.timeout_loss_count == 1
    assert summary.timeout_avg_net == pytest.approx(0.002 / 3)
    assert summary.recommendation == "HIGH_CONCENTRATION_RISK"


def test_paper_profit_concentration_handles_empty_dataset(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    summary = PaperProfitConcentrationEngine(database).build_summary(
        profile="mean_reversion_hf_micro_v1",
    )

    assert summary.realized_cycles_count == 0
    assert summary.total_net_profit == 0.0
    assert summary.top1_profit_share == 0.0
    assert summary.recommendation == "NO_DATA"
