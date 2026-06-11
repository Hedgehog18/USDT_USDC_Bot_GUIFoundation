from analytics.entry_threshold_sensitivity_engine import EntryThresholdSensitivityEngine
from storage.database_manager import DatabaseManager


def _insert_snapshot(
    conn,
    index: int,
    work_position: float,
    micro_trend: str,
    price: float = 1.0,
    spread: float = 0.00001,
    market_health_score: float = 100.0,
    market_health_status: str = "HEALTHY",
    market_regime: str = "NORMAL",
    volatility_regime: str = "LOW",
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
            f"2026-01-01T00:0{index}:00",
            "USDCUSDT",
            price,
            price - 0.00001,
            price + 0.00001,
            spread,
            1.0,
            work_position,
            1.0,
            50.0,
            1.0,
            50.0,
            "LOW",
            "MIXED",
            80.0,
            market_regime,
            0.8,
            0.7,
            0.9,
            0.6,
            0.5,
            0.1,
            "BALANCED",
            micro_trend,
            0.00001,
            volatility_regime,
            market_health_score,
            market_health_status,
            "OK",
        ),
    )


def test_entry_threshold_sensitivity_empty_database(test_config, tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    report = EntryThresholdSensitivityEngine(database, test_config).build_report()

    assert report.profile == "mean_reversion_v1"
    assert report.variants[0].total_samples == 0
    assert report.fee_rates.maker == 0.0
    assert report.fee_rates.taker == 0.0


def test_entry_threshold_sensitivity_wider_thresholds_create_more_candidates(test_config, tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    with database.connect() as conn:
        _insert_snapshot(conn, 0, 18.0, "BUY_DOMINANT")
        _insert_snapshot(conn, 1, 25.0, "BUY_DOMINANT")
        _insert_snapshot(conn, 2, 75.0, "SELL_DOMINANT")
        _insert_snapshot(conn, 3, 50.0, "NEUTRAL")
        _insert_snapshot(conn, 4, 15.0, "SELL_DOMINANT")
        conn.commit()

    report = EntryThresholdSensitivityEngine(database, test_config).build_report(
        variants=((20.0, 80.0), (25.0, 75.0)),
    )
    strict, wider = report.variants

    assert strict.total_samples == 5
    assert strict.buy_zone_count == 2
    assert strict.sell_zone_count == 0
    assert strict.candidate_count == 1
    assert strict.micro_trend_pass_count == 1
    assert ("micro_trend", 1) in strict.remaining_blockers
    assert strict.risk_profitability_pass_count == 1
    assert strict.min_notional_pass_count == 1
    assert strict.net_profit_min is not None
    assert strict.net_profit_min > 0

    assert wider.buy_zone_count == 3
    assert wider.sell_zone_count == 1
    assert wider.candidate_count == 3
    assert wider.expected_trade_frequency == 3 / 5
