import pytest

from analytics.hf_run_regime_comparison_engine import HFRunRegimeComparisonEngine
from storage.database_manager import DatabaseManager


def _insert_cycle(
    database: DatabaseManager,
    *,
    db_id: int,
    profile: str = "mean_reversion_hf_micro_v1",
    direction: str = "BUY_USDC",
    net_profit: float = 0.0001,
    close_reason: str = "target",
    opened_at: str | None = None,
    closed_at: str | None = None,
    max_favorable_pnl: float = 0.0001,
    max_adverse_pnl: float = -0.00005,
    was_target_touched: int = 1,
    was_near_target: int = 0,
    with_context: bool = True,
    current_price: float = 1.0001,
    short_center: float = 1.0000,
    previous_price: float = 1.0000,
    last_different_price: float = 1.0000,
    hf_entry_mode: str = "short_center_direct",
    price_buffer_unique_values: int = 3,
    flat_samples_count: int = 0,
    flat_price_buffer: int = 0,
) -> None:
    opened_at = opened_at or f"2026-07-02T12:{db_id % 60:02d}:00"
    closed_at = closed_at or f"2026-07-02T12:{db_id % 60:02d}:30"
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO paper_cycles (
                id, timestamp, cycle_id, strategy_profile, direction, status,
                open_price, close_price, quantity, open_fee, close_fee,
                gross_profit, net_profit, opened_at, closed_at, close_reason,
                max_favorable_pnl, max_adverse_pnl, was_target_touched, was_near_target
            ) VALUES (?, ?, ?, ?, ?, 'CLOSED',
                      1.0000, 1.0001, 10, 0, 0, ?, ?, ?, ?, ?,
                      ?, ?, ?, ?)
            """,
            (
                db_id,
                opened_at,
                db_id,
                profile,
                direction,
                net_profit,
                net_profit,
                opened_at,
                closed_at,
                close_reason,
                max_favorable_pnl,
                max_adverse_pnl,
                was_target_touched,
                was_near_target,
            ),
        )
        if with_context:
            conn.execute(
                """
                INSERT INTO hf_paper_cycle_entry_diagnostics (
                    paper_cycle_id, timestamp, strategy_profile, current_price,
                    short_center, previous_price, last_different_price,
                    hf_entry_mode, price_buffer_unique_values, flat_samples_count,
                    flat_price_buffer, entry_direction, entry_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    db_id,
                    opened_at,
                    profile,
                    current_price,
                    short_center,
                    previous_price,
                    last_different_price,
                    hf_entry_mode,
                    price_buffer_unique_values,
                    flat_samples_count,
                    flat_price_buffer,
                    direction,
                    hf_entry_mode,
                ),
            )
        conn.commit()


def test_hf_run_regime_comparison_since_id_and_breakdowns(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _insert_cycle(database, db_id=1, net_profit=0.5)
    _insert_cycle(database, db_id=2, direction="BUY_USDC", net_profit=0.1)
    _insert_cycle(database, db_id=3, direction="SELL_USDC", net_profit=-0.2, close_reason="max_holding_270s")
    _insert_cycle(database, db_id=10, direction="SELL_USDC", net_profit=0.3)

    report = HFRunRegimeComparisonEngine(database).compare(
        profile="mean_reversion_hf_micro_v1",
        run_a_since_id=1,
        run_b_since_id=9,
    )

    assert report.run_a.cycles_count == 2
    assert report.run_a.net_profit == pytest.approx(-0.1)
    assert report.run_a.buy.count == 1
    assert report.run_a.sell.count == 1
    assert report.run_a.sell.timeout_loss_count == 1
    assert report.run_b.cycles_count == 1


def test_hf_run_regime_comparison_missing_entry_context_handled(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _insert_cycle(database, db_id=1, with_context=False)

    report = HFRunRegimeComparisonEngine(database).compare(
        profile="mean_reversion_hf_micro_v1",
        run_a_since_id=0,
        run_b_since_id=100,
    )

    assert report.run_a.entry_context.available_count == 0
    assert report.run_a.entry_context.missing_count == 1
    assert report.run_b.cycles_count == 0
    assert report.recommendation == "NEED_MORE_DATA"


def test_hf_run_regime_comparison_flat_velocity_and_recommendation(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    for index in range(1, 21):
        _insert_cycle(
            database,
            db_id=index,
            net_profit=0.0002,
            current_price=1.0002,
            previous_price=1.0001,
            last_different_price=1.0001,
            price_buffer_unique_values=4,
            flat_samples_count=0,
        )
    for index in range(101, 121):
        _insert_cycle(
            database,
            db_id=index,
            net_profit=-0.0001,
            close_reason="max_holding_270s",
            max_favorable_pnl=0.0,
            max_adverse_pnl=-0.0002,
            was_target_touched=0,
            current_price=1.0001,
            previous_price=1.0001,
            last_different_price=1.0001,
            price_buffer_unique_values=1,
            flat_samples_count=5,
            flat_price_buffer=1,
            hf_entry_mode="flat_no_trade",
        )

    report = HFRunRegimeComparisonEngine(database).compare(
        profile="mean_reversion_hf_micro_v1",
        run_a_since_id=0,
        run_b_since_id=100,
        limit=20,
    )

    assert report.run_a.entry_context.average_price_velocity == pytest.approx(0.0001)
    assert report.run_b.entry_context.average_flat_samples_count == pytest.approx(5.0)
    assert report.run_b.entry_context.average_price_buffer_unique_values == pytest.approx(1.0)
    assert report.run_b.loss_diagnostics.categories["flat_market_entry"] == 20
    assert "Run B has higher flat_samples_count." in report.differences
    assert report.recommendation == "ADD_MARKET_REGIME_FILTER"
