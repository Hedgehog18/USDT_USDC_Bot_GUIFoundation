from analytics.extreme_paper_signal_diagnostics_engine import ExtremePaperSignalDiagnosticsEngine
from storage.database_manager import DatabaseManager


def _insert_cycle(
    database: DatabaseManager,
    *,
    profile: str = "extreme_strategy_v1",
    direction: str = "SELL_USDC",
    open_price: float = 1.0008,
    close_price: float = 1.0009,
    net_profit: float = -0.001,
    close_reason: str = "extreme_timeout",
    opened_at: str = "2026-07-02T18:00:00",
    closed_at: str = "2026-07-02T18:01:00",
    max_favorable: float = 0.0,
    max_adverse: float = -0.001,
    min_distance: float = 0.00001,
    was_near_target: int = 0,
) -> int:
    with database.connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO paper_cycles (
                timestamp, cycle_id, strategy_profile, direction, status,
                open_price, close_price, quantity, open_fee, close_fee,
                gross_profit, net_profit, opened_at, closed_at, close_reason,
                max_favorable_pnl, max_adverse_pnl, min_distance_to_target, was_near_target
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                opened_at,
                1,
                profile,
                direction,
                "CLOSED",
                open_price,
                close_price,
                10.0,
                0.0,
                0.0,
                net_profit,
                net_profit,
                opened_at,
                closed_at,
                close_reason,
                max_favorable,
                max_adverse,
                min_distance,
                was_near_target,
            ),
        )
        return int(cursor.lastrowid)


def _insert_extreme_entry_diagnostics(
    database: DatabaseManager,
    cycle_id: int,
    *,
    entry_direction: str = "SELL_USDC",
    session_signal: bool = True,
    velocity_spike_signal: bool = True,
    compression_signal: bool = True,
    signal_strength: float = 70.0,
    lead_warning: str = "no",
    expected_direction: str = "SELL_USDC",
    velocity_value: float = -0.0000012,
    velocity_threshold: float = 0.000001,
    compression_score: float = 80.0,
    compression_threshold: float = 60.0,
) -> None:
    database.save_hf_paper_cycle_entry_diagnostics(
        paper_cycle_id=cycle_id,
        strategy_profile="extreme_strategy_v1",
        current_price=1.0008,
        short_center=1.0008,
        previous_price=1.00081,
        last_different_price=1.00081,
        hf_entry_mode="extreme_immediate_entry",
        price_buffer_unique_values=2,
        flat_samples_count=5,
        flat_price_buffer=False,
        entry_direction=entry_direction,
        entry_reason="extreme signal confirmed",
        session_signal=session_signal,
        velocity_spike_signal=velocity_spike_signal,
        compression_signal=compression_signal,
        signal_strength=signal_strength,
        lead_warning=lead_warning,
        expected_direction=expected_direction,
        velocity_value=velocity_value,
        velocity_threshold=velocity_threshold,
        compression_score=compression_score,
        compression_threshold=compression_threshold,
    )


def test_extreme_paper_signal_diagnostics_categorizes_false_positive(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    cycle_id = _insert_cycle(database, net_profit=-0.001)
    _insert_extreme_entry_diagnostics(database, cycle_id)

    report = ExtremePaperSignalDiagnosticsEngine(database).build_report()

    assert report.total_cycles == 1
    assert report.false_positives == 1
    assert report.cycles[0].false_positive_category == "weak_velocity_spike"
    assert report.cycles[0].velocity_spike_signal == "yes"


def test_extreme_paper_signal_diagnostics_winner_loser_summary(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    winner_id = _insert_cycle(
        database,
        close_price=1.0007,
        net_profit=0.002,
        close_reason="extreme_target",
        max_favorable=0.002,
    )
    loser_id = _insert_cycle(database, net_profit=-0.001, close_reason="extreme_timeout")
    _insert_extreme_entry_diagnostics(
        database,
        winner_id,
        signal_strength=90.0,
        velocity_value=-0.000003,
        compression_score=100.0,
    )
    _insert_extreme_entry_diagnostics(
        database,
        loser_id,
        signal_strength=50.0,
        velocity_value=-0.000001,
        compression_score=70.0,
    )

    report = ExtremePaperSignalDiagnosticsEngine(database).build_report()

    assert report.total_cycles == 2
    assert report.target_closed == 1
    assert report.timeout_closed == 1
    assert report.average_signal_strength_winners == 90.0
    assert report.average_signal_strength_losers == 50.0
    assert report.average_velocity_winners == -0.000003
    assert report.average_compression_losers == 70.0


def test_extreme_paper_signal_diagnostics_handles_missing_diagnostics(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _insert_cycle(database, net_profit=-0.001)

    report = ExtremePaperSignalDiagnosticsEngine(database).build_report()

    assert report.total_cycles == 1
    assert report.cycles[0].session_signal == "N/A"
    assert report.cycles[0].velocity_value is None
    assert report.cycles[0].false_positive_category == "unknown"


def test_extreme_paper_signal_diagnostics_empty_dataset(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    report = ExtremePaperSignalDiagnosticsEngine(database).build_report()

    assert report.total_cycles == 0
    assert report.recommendation == "NEED_MORE_DATA"
    assert report.cycles == []
