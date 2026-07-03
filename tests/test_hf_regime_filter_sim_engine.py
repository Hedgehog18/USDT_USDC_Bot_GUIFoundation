import pytest

from analytics.hf_regime_filter_sim_engine import (
    HFRegimeFilterSimulationEngine,
    REGIME_NAMES,
)
from analytics.hf_velocity_filter_sim_engine import HFVelocityCycle
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
    price_buffer_unique_values: int | None = 3,
    flat_samples_count: int | None = 0,
    flat_price_buffer: int | None = 0,
    hf_entry_mode: str = "short_center_direct",
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
        conn.execute(
            """
            INSERT INTO hf_paper_cycle_entry_diagnostics (
                paper_cycle_id, timestamp, strategy_profile, current_price,
                short_center, previous_price, last_different_price,
                hf_entry_mode, price_buffer_unique_values, flat_samples_count,
                flat_price_buffer, entry_direction, entry_reason
            ) VALUES (?, ?, ?, ?, 1.0000, ?, ?, ?, ?, ?, ?, ?, 'test')
            """,
            (
                db_id,
                opened_at,
                profile,
                current_price,
                previous_price,
                last_different_price,
                hf_entry_mode,
                price_buffer_unique_values,
                flat_samples_count,
                flat_price_buffer,
                direction,
            ),
        )
        conn.commit()


def _cycle(**overrides):
    defaults = dict(
        db_id=1,
        direction="BUY_USDC",
        net_profit=0.0,
        close_price=1.0000,
        close_reason="target",
        opened_at=None,
        closed_at=None,
        current_price=1.0001,
        previous_price=1.0000,
        last_different_price=1.0000,
        short_center=1.0000,
        hf_entry_mode="short_center_direct",
        price_buffer_unique_values=3,
        flat_samples_count=0,
        flat_price_buffer=False,
    )
    defaults.update(overrides)
    return HFVelocityCycle(**defaults)


def test_hf_regime_filter_classification_works(tmp_path):
    engine = HFRegimeFilterSimulationEngine(DatabaseManager(str(tmp_path / "bot.sqlite")))

    assert engine.classify_cycle(_cycle(flat_price_buffer=True)) == "FLAT"
    assert engine.classify_cycle(_cycle(current_price=1.00003, previous_price=1.00000)) == "HIGH_VELOCITY"
    assert engine.classify_cycle(_cycle(current_price=1.00001, previous_price=1.00000, last_different_price=0.99998)) == "FAST_DRIFT"
    assert engine.classify_cycle(_cycle(current_price=1.000015, previous_price=1.00000, last_different_price=1.00000)) == "SLOW_DRIFT"
    assert engine.classify_cycle(_cycle(current_price=1.000005, previous_price=1.00000, price_buffer_unique_values=2)) == "MICRO_RANGE"
    assert engine.classify_cycle(_cycle(current_price=1.000005, previous_price=1.00000, last_different_price=1.00000)) == "LOW_VELOCITY"
    assert engine.classify_cycle(_cycle(current_price=None)) == "UNKNOWN"


def test_hf_regime_filter_simulates_velocity_filter_inside_each_regime(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _insert_cycle(
        database,
        db_id=1,
        net_profit=-0.0002,
        close_reason="max_holding_270s",
        current_price=1.00003,
        previous_price=1.00000,
    )
    _insert_cycle(
        database,
        db_id=2,
        net_profit=0.0001,
        current_price=1.000005,
        previous_price=1.00000,
    )
    _insert_cycle(
        database,
        db_id=3,
        net_profit=0.0001,
        current_price=1.0000,
        previous_price=1.0000,
        flat_price_buffer=1,
        price_buffer_unique_values=1,
        hf_entry_mode="flat_no_trade",
    )

    report = HFRegimeFilterSimulationEngine(database).simulate(
        profile="mean_reversion_hf_micro_v1",
        since_id=0,
    )

    high_velocity = next(item for item in report.regimes if item.regime == "HIGH_VELOCITY")
    flat = next(item for item in report.regimes if item.regime == "FLAT")
    assert high_velocity.cycles_count == 1
    assert high_velocity.filter_result.blocked_cycles == 1
    assert high_velocity.filter_result.net_improvement_vs_baseline == pytest.approx(0.0002)
    assert flat.cycles_count == 1
    assert flat.filter_result.blocked_cycles == 0


def test_hf_regime_filter_empty_regimes_and_conclusion(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    report = HFRegimeFilterSimulationEngine(database).simulate(
        profile="mean_reversion_hf_micro_v1",
        since_id=0,
    )

    assert report.total_cycles == 0
    assert [item.regime for item in report.regimes] == list(REGIME_NAMES)
    assert all(item.cycles_count == 0 for item in report.regimes)
    assert report.best_regime is None
    assert report.conclusion == "No cycles available. Need more data."


def test_hf_regime_filter_generates_recommendation(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    for db_id in range(1, 6):
        _insert_cycle(
            database,
            db_id=db_id,
            net_profit=-0.0002,
            close_reason="max_holding_270s",
            current_price=1.00003,
            previous_price=1.00000,
        )
    for db_id in range(6, 11):
        _insert_cycle(
            database,
            db_id=db_id,
            net_profit=0.0001,
            current_price=1.000005,
            previous_price=1.00000,
        )

    report = HFRegimeFilterSimulationEngine(database).simulate(
        profile="mean_reversion_hf_micro_v1",
        since_id=0,
    )

    assert report.best_regime == "HIGH_VELOCITY"
    assert "HIGH_VELOCITY" in report.conclusion
