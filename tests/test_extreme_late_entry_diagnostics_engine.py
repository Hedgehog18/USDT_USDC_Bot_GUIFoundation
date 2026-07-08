from analytics.extreme_late_entry_diagnostics_engine import ExtremeLateEntryDiagnosticsEngine
from storage.database_manager import DatabaseManager


def _insert_cycle(
    database: DatabaseManager,
    *,
    db_id: int,
    open_price: float,
    close_price: float,
    net_profit: float,
    lead_warning: str | None = None,
) -> None:
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO paper_cycles (
                id, timestamp, cycle_id, strategy_profile, direction, status,
                open_price, close_price, quantity, open_fee, close_fee,
                gross_profit, net_profit, opened_at, closed_at, close_reason
            ) VALUES (?, ?, ?, 'extreme_strategy_v1', 'SELL_USDC', 'CLOSED',
                      ?, ?, 10, 0, 0, ?, ?, ?, ?, 'extreme_timeout')
            """,
            (
                db_id,
                f"2026-07-02T18:{db_id % 60:02d}:00",
                db_id,
                open_price,
                close_price,
                net_profit,
                net_profit,
                f"2026-07-02T18:{db_id % 60:02d}:00",
                f"2026-07-02T18:{db_id % 60:02d}:59",
            ),
        )
        if lead_warning is not None:
            conn.execute(
                """
                INSERT INTO hf_paper_cycle_entry_diagnostics (
                    paper_cycle_id, timestamp, strategy_profile, current_price,
                    hf_entry_mode, entry_direction, entry_reason,
                    signal_strength, lead_warning, expected_direction,
                    velocity_value, velocity_threshold, compression_score
                ) VALUES (?, ?, 'extreme_strategy_v1', ?,
                          'extreme_immediate_entry', 'SELL_USDC', 'extreme signal confirmed',
                          80.0, ?, 'SELL_USDC', -0.000002, 0.000001, 100.0)
                """,
                (
                    db_id,
                    f"2026-07-02T18:{db_id % 60:02d}:00",
                    open_price,
                    lead_warning,
                ),
            )
        conn.commit()


def test_extreme_late_entry_diagnostics_counts_extreme_price_loss(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _insert_cycle(
        database,
        db_id=1981,
        open_price=0.99992000,
        close_price=1.00048500,
        net_profit=-0.00565023,
        lead_warning="yes",
    )
    _insert_cycle(
        database,
        db_id=1982,
        open_price=1.00080000,
        close_price=1.00079000,
        net_profit=0.00010000,
        lead_warning="no",
    )

    report = ExtremeLateEntryDiagnosticsEngine(database).build_report()

    assert report.total_cycles == 2
    assert report.late_entry_cycles[0].db_id == 1981
    assert report.extreme_price_entry_cycles[0].db_id == 1981
    assert report.late_entry_loss_contribution == -0.00565023
    assert report.extreme_price_entry_loss_contribution == -0.00565023
    assert abs(report.net_without_late_entry_cycles - 0.00010000) < 0.00000001
    assert abs(report.net_without_extreme_price_entries - 0.00010000) < 0.00000001
    assert report.worst_cycle.db_id == 1981


def test_extreme_late_entry_diagnostics_empty_dataset(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    report = ExtremeLateEntryDiagnosticsEngine(database).build_report()

    assert report.total_cycles == 0
    assert report.recommendation == "NEED_MORE_DATA"
    assert report.late_entry_cycles == []
