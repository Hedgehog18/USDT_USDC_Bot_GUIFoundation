import pytest

from analytics.hf_collection_extreme_metrics import HFCollectionExtremeMetricsEngine
from analytics.hf_extreme_price import is_extreme_close_price
from storage.database_manager import DatabaseManager


def _insert_cycle(
    database: DatabaseManager,
    *,
    db_id: int,
    close_price: float,
    net_profit: float,
    profile: str = "mean_reversion_hf_micro_v1",
    status: str = "CLOSED",
) -> None:
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO paper_cycles (
                id, timestamp, cycle_id, strategy_profile, direction, status,
                open_price, close_price, quantity, open_fee, close_fee,
                gross_profit, net_profit, opened_at, closed_at, close_reason
            ) VALUES (?, ?, ?, ?, 'SELL_USDC', ?, 1.000835, ?, 10, 0, 0, ?, ?, ?, ?, 'target')
            """,
            (
                db_id,
                f"2026-07-02T12:{db_id:02d}:00",
                db_id,
                profile,
                status,
                close_price,
                net_profit,
                net_profit,
                f"2026-07-02T12:{db_id:02d}:00",
                f"2026-07-02T12:{db_id:02d}:10",
            ),
        )
        conn.commit()


def test_shared_extreme_close_price_helper_detects_known_value():
    assert is_extreme_close_price(0.99992000) is True
    assert is_extreme_close_price(1.00000000) is False


def test_hf_collection_extreme_metrics_exclude_extreme_cycle(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _insert_cycle(database, db_id=1, close_price=1.00084000, net_profit=-0.0001)
    _insert_cycle(database, db_id=2, close_price=0.99992000, net_profit=0.00914618)

    stats = {"closed_cycles": 2, "net_profit": 0.00904618, "win_rate": 0.5}
    enriched = HFCollectionExtremeMetricsEngine(database).enrich_stats(
        stats,
        "mean_reversion_hf_micro_v1",
        baseline_max_id=0,
    )

    assert enriched["extreme_cycles"] == 1
    assert enriched["non_extreme_cycles"] == 1
    assert enriched["extreme_profit"] == pytest.approx(0.00914618)
    assert enriched["net_profit_without_extreme"] == pytest.approx(-0.0001)
    assert enriched["net_profit"] == pytest.approx(
        enriched["net_profit_without_extreme"] + enriched["extreme_profit"]
    )
    assert enriched["win_rate_without_extreme"] == pytest.approx(0.0)
    assert enriched["extreme_recommendation"] == "EXTREME_DEPENDENT_RUN"
    assert "WARNING" in enriched["extreme_warning"]


def test_hf_collection_extreme_metrics_baseline_and_empty_run(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _insert_cycle(database, db_id=1, close_price=0.99992000, net_profit=0.1)
    _insert_cycle(database, db_id=2, close_price=1.00010000, net_profit=0.2)

    enriched = HFCollectionExtremeMetricsEngine(database).enrich_stats(
        {"closed_cycles": 1, "net_profit": 0.2, "win_rate": 1.0},
        "mean_reversion_hf_micro_v1",
        baseline_max_id=1,
    )
    assert enriched["extreme_cycles"] == 0
    assert enriched["net_profit_without_extreme"] == pytest.approx(0.2)
    assert enriched["extreme_recommendation"] == "NORMAL_HF_RUN"

    empty = HFCollectionExtremeMetricsEngine(database).enrich_stats(
        {"closed_cycles": 0, "net_profit": 0.0, "win_rate": 0.0},
        "missing_profile",
        baseline_max_id=0,
    )
    assert empty["extreme_cycles"] == 0
    assert empty["non_extreme_cycles"] == 0
    assert empty["net_profit_without_extreme"] == pytest.approx(0.0)
