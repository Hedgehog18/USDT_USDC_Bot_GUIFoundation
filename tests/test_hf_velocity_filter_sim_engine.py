import pytest

from analytics.hf_velocity_filter_sim_engine import HFVelocityFilterSimulationEngine
from storage.database_manager import DatabaseManager


def _insert_cycle(
    database: DatabaseManager,
    *,
    db_id: int,
    profile: str = "mean_reversion_hf_micro_v1",
    direction: str = "BUY_USDC",
    net_profit: float = 0.0001,
    close_price: float = 1.0001,
    close_reason: str = "target",
    current_price: float | None = 1.0001,
    previous_price: float | None = 1.0000,
    last_different_price: float | None = 1.0000,
    with_context: bool = True,
) -> None:
    opened_at = f"2026-07-02T12:{db_id % 60:02d}:00"
    closed_at = f"2026-07-02T12:{db_id % 60:02d}:30"
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO paper_cycles (
                id, timestamp, cycle_id, strategy_profile, direction, status,
                open_price, close_price, quantity, open_fee, close_fee,
                gross_profit, net_profit, opened_at, closed_at, close_reason
            ) VALUES (?, ?, ?, ?, ?, 'CLOSED',
                      1.0000, ?, 10, 0, 0, ?, ?, ?, ?, ?)
            """,
            (
                db_id,
                opened_at,
                db_id,
                profile,
                direction,
                close_price,
                net_profit,
                net_profit,
                opened_at,
                closed_at,
                close_reason,
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
                ) VALUES (?, ?, ?, ?, 1.0000, ?, ?, 'short_center_direct', 3, 0, 0, ?, 'test')
                """,
                (
                    db_id,
                    opened_at,
                    profile,
                    current_price,
                    previous_price,
                    last_different_price,
                    direction,
                ),
            )
        conn.commit()


def _scenario(report, name: str):
    return next(item for item in report.scenarios if item.scenario == name)


def test_hf_velocity_filter_threshold_blocks_expected_cycles(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _insert_cycle(database, db_id=1, current_price=1.00003, previous_price=1.00000)
    _insert_cycle(database, db_id=2, current_price=1.000005, previous_price=1.00000)

    report = HFVelocityFilterSimulationEngine(database).simulate(
        profile="mean_reversion_hf_micro_v1",
        since_id=0,
    )

    result = _scenario(report, "block_velocity_gt_0.00001")
    assert result.blocked_cycles == 1
    assert result.kept_cycles == 1


def test_hf_velocity_filter_direction_confirmation_and_adverse_drift(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _insert_cycle(
        database,
        db_id=1,
        direction="BUY_USDC",
        net_profit=-0.0002,
        close_reason="max_holding_270s",
        current_price=0.9999,
        previous_price=1.0000,
        last_different_price=1.0000,
    )
    _insert_cycle(
        database,
        db_id=2,
        direction="SELL_USDC",
        net_profit=-0.0002,
        close_reason="max_holding_270s",
        current_price=1.0001,
        previous_price=1.0000,
        last_different_price=1.0000,
    )
    _insert_cycle(
        database,
        db_id=3,
        direction="SELL_USDC",
        net_profit=0.0003,
        current_price=0.9999,
        previous_price=1.0000,
        last_different_price=1.0000,
    )

    report = HFVelocityFilterSimulationEngine(database).simulate(
        profile="mean_reversion_hf_micro_v1",
        since_id=0,
    )

    confirmation = _scenario(report, "block_unconfirmed_direction")
    adverse = _scenario(report, "block_adverse_drift_only")
    assert confirmation.blocked_cycles == 2
    assert confirmation.blocked_losers == 2
    assert adverse.blocked_cycles == 2
    assert adverse.timeout_losses_blocked == 2
    assert adverse.net_improvement_vs_baseline == pytest.approx(0.0004)


def test_hf_velocity_filter_extreme_cycles_excluded_from_main_comparison(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _insert_cycle(database, db_id=1, net_profit=0.01, close_price=0.99992000, current_price=1.0001, previous_price=1.0000)
    _insert_cycle(database, db_id=2, net_profit=-0.0002, current_price=0.9999, previous_price=1.0000)

    report = HFVelocityFilterSimulationEngine(database).simulate(
        profile="mean_reversion_hf_micro_v1",
        since_id=0,
    )

    result = _scenario(report, "block_unconfirmed_direction")
    assert report.baseline_net_without_extreme == pytest.approx(-0.0002)
    assert result.net_kept_without_extreme == pytest.approx(0.0)
    assert result.extreme_net_kept == pytest.approx(0.01)


def test_hf_velocity_filter_empty_dataset_handled(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    report = HFVelocityFilterSimulationEngine(database).simulate(
        profile="mean_reversion_hf_micro_v1",
        since_id=0,
    )

    assert report.cycles_count == 0
    assert report.scenarios[0].recommendation == "DO_NOT_USE"
