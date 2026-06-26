from analytics.high_frequency_diagnostics_engine import HighFrequencyDiagnosticsEngine
from storage.database_manager import DatabaseManager


def _insert_snapshot(
    conn,
    *,
    index: int,
    price: float,
    work_position: float,
    short_center: float,
    micro_trend: str,
    spread: float = 0.00001,
) -> None:
    conn.execute(
        """
        INSERT INTO market_snapshots (
            timestamp, symbol, price, bid, ask, spread,
            work_center, work_position,
            short_center, short_position,
            long_center, long_position,
            center_confidence, center_alignment,
            market_activity_score, market_regime,
            corridor_quality_score, mean_reversion_score,
            spread_stability_score, center_crossing_score,
            tick_activity_score, order_book_imbalance,
            order_book_pressure, micro_trend,
            relative_volatility, volatility_regime,
            market_health_score, market_health_status, market_health_reason
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            f"2026-01-01T00:{index:02d}:00",
            "USDCUSDT",
            price,
            price - 0.00001,
            price + 0.00001,
            spread,
            1.0,
            work_position,
            short_center,
            50.0,
            1.0,
            50.0,
            "LOW",
            "MIXED",
            80.0,
            "NORMAL",
            0.8,
            0.7,
            0.9,
            0.6,
            0.5,
            0.1,
            "BALANCED",
            micro_trend,
            0.00001,
            "LOW",
            100.0,
            "HEALTHY",
            "OK",
        ),
    )


def test_high_frequency_diagnostics_builds_research_summary(test_config, tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    prices = [1.00000, 0.99998, 1.00002, 1.00005, 1.00001, 0.99996]
    with database.connect() as conn:
        for index, price in enumerate(prices):
            _insert_snapshot(
                conn,
                index=index,
                price=price,
                work_position=20.0 if index == 1 else 50.0,
                short_center=1.0,
                micro_trend="BUY_DOMINANT" if index == 1 else "NEUTRAL",
            )
        conn.commit()

    report = HighFrequencyDiagnosticsEngine(database, test_config).build_report()

    assert report.total_samples == len(prices)
    assert report.estimated_sample_interval_seconds == 60.0
    assert report.current_candidate_count == 1
    assert report.current_blockers[0].name == "entry_zone_work_position"
    assert {item.name for item in report.micro_entry_scenarios} >= {
        "current_mean_reversion",
        "micro_movement_only",
        "spread_only",
        "short_term_mean_reversion",
    }
    assert len(report.target_results) == 5
    assert report.target_results[0].target_percent == 0.001
    assert report.potential_cycles_per_day >= 0.0
    assert report.better_fit in {"Current Mean Reversion", "Potential High Frequency"}
