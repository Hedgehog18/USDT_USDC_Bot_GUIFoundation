from analytics.extreme_replay_engine import (
    ExtremeReplayEventResult,
    ExtremeReplayReport,
    ExtremeReplayScenarioResult,
    ExtremeReplayStatistics,
)
from analytics.extreme_replay_ranking_engine import ExtremeReplayRankingEngine
from storage.database_manager import DatabaseManager


def _insert_cycle(
    database: DatabaseManager,
    *,
    db_id: int,
    opened_at: str,
    closed_at: str,
    close_price: float = 0.99992000,
    open_price: float = 1.00000000,
) -> None:
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO paper_cycles (
                id, timestamp, cycle_id, strategy_profile, direction, status,
                open_price, close_price, quantity, open_fee, close_fee,
                gross_profit, net_profit, opened_at, closed_at, close_reason
            ) VALUES (?, ?, ?, 'mean_reversion_hf_micro_v1', 'SELL_USDC', 'CLOSED',
                      ?, ?, 10, 0, 0, 0.001, 0.001, ?, ?, 'target')
            """,
            (db_id, opened_at, db_id, open_price, close_price, opened_at, closed_at),
        )
        conn.commit()


def _snapshot(timestamp: str, *, price: float) -> dict:
    return {
        "timestamp": timestamp,
        "symbol": "USDCUSDT",
        "price": price,
        "bid": price - 0.000005,
        "ask": price + 0.000005,
        "mid_price": price,
        "spread": 0.00001,
        "work_position": 50.0,
        "micro_trend": "NEUTRAL",
        "entry_zone": "CENTER",
        "buy_zone": 0,
        "sell_zone": 0,
        "volatility_regime": "NORMAL",
        "market_regime": "NORMAL",
        "distance_to_long_center": 0.0,
        "distance_to_short_center": 0.00001,
        "distance_to_work_center": 0.0,
        "order_book_pressure": "BALANCED",
        "session": "NEW_YORK",
        "price_change_5_sec": 0.0,
        "price_change_10_sec": 0.0,
        "price_change_30_sec": 0.0,
        "price_change_1_min": 0.0,
        "price_change_5_min": 0.0,
        "would_open_cycle": 0,
        "reason_if_not": "test",
        "data_source": "BINANCE",
    }


def _scenario(name: str, profit: float, mae: float, rr: float | None = None) -> ExtremeReplayScenarioResult:
    return ExtremeReplayScenarioResult(
        scenario=name,
        entered=True,
        entry_timestamp="2026-07-02T10:00:00",
        direction="SELL_USDC",
        entry_price=1.0,
        exit_price=1.0 - profit,
        maximum_favorable_excursion=profit,
        maximum_adverse_excursion=mae,
        recovery_seconds=30.0,
        holding_seconds=60.0,
        distance_travelled=profit,
        potential_profit=profit,
        potential_loss=mae,
        reward_risk=rr if rr is not None else (profit / mae if mae > 0 else None),
    )


def _event(number: int, scenario: ExtremeReplayScenarioResult, *, cluster: str = "Single", session: str = "NEW_YORK"):
    return ExtremeReplayEventResult(
        event_number=number,
        db_id=number,
        start_timestamp="2026-07-02T10:00:00",
        end_timestamp="2026-07-02T10:01:00",
        duration_seconds=60.0,
        amplitude_class="Micro Extreme",
        session=session,
        cluster_label=cluster,
        scenarios=[scenario],
    )


def _report(events: list[ExtremeReplayEventResult]) -> ExtremeReplayReport:
    return ExtremeReplayReport(
        profile="mean_reversion_hf_micro_v1",
        events=events,
        statistics=ExtremeReplayStatistics(
            events_count=len(events),
            scenario_count=sum(len(event.scenarios) for event in events),
            entered_replays_count=sum(1 for event in events for scenario in event.scenarios if scenario.entered),
            average_potential_profit=None,
            median_potential_profit=None,
            average_adverse_excursion=None,
            average_favorable_excursion=None,
            average_reward_risk=None,
            reward_risk_distribution={},
            assessment="test",
        ),
        report_path="reports/test.txt",
    )


def test_extreme_replay_ranking_orders_by_stability_score(tmp_path):
    engine = ExtremeReplayRankingEngine(DatabaseManager(str(tmp_path / "bot.sqlite")))
    stable_events = [
        _event(index, _scenario("stable", 0.0005, 0.00001), cluster="Single", session="NEW_YORK")
        for index in range(1, 16)
    ]
    concentrated_events = [
        _event(100, _scenario("concentrated", 0.0040, 0.00001), cluster="Cluster", session="NEW_YORK"),
        *[
            _event(100 + index, _scenario("concentrated", 0.00005, 0.00001), cluster="Cluster", session="NEW_YORK")
            for index in range(1, 15)
        ],
    ]

    rankings = engine.rank_replay_report(_report(stable_events + concentrated_events))

    assert rankings[0].scenario_name == "stable"
    assert rankings[0].stability_score > rankings[1].stability_score


def test_extreme_replay_ranking_calculates_concentration_median_and_worst_mae(tmp_path):
    engine = ExtremeReplayRankingEngine(DatabaseManager(str(tmp_path / "bot.sqlite")))
    events = [
        _event(1, _scenario("scenario", 0.0010, 0.00001)),
        _event(2, _scenario("scenario", 0.0002, 0.00003)),
        _event(3, _scenario("scenario", 0.0002, 0.00002)),
    ]

    ranking = engine.rank_replay_report(_report(events))[0]

    assert ranking.median_potential_profit == 0.0002
    assert ranking.worst_mae == 0.00003
    assert ranking.best_event_contribution_share == (0.0010 / 0.0014)
    assert ranking.top3_event_contribution_share == 1.0


def test_extreme_replay_ranking_generates_recommendations(tmp_path):
    engine = ExtremeReplayRankingEngine(DatabaseManager(str(tmp_path / "bot.sqlite")))
    strong_events = [
        _event(index, _scenario("strong", 0.0008, 0.0), cluster="Single", session="NEW_YORK")
        for index in range(1, 31)
    ]
    risky_events = [
        _event(index + 100, _scenario("risky", 0.0008, 0.0003), cluster="Single", session="NEW_YORK")
        for index in range(1, 31)
    ]

    rankings = {item.scenario_name: item for item in engine.rank_replay_report(_report(strong_events + risky_events))}

    assert rankings["strong"].recommendation == "STRONG_REPLAY_CANDIDATE"
    assert rankings["risky"].recommendation == "REJECT"


def test_extreme_replay_ranking_empty_dataset(tmp_path):
    engine = ExtremeReplayRankingEngine(DatabaseManager(str(tmp_path / "bot.sqlite")))

    rankings = engine.rank_replay_report(_report([]))

    assert rankings == []


def test_extreme_replay_ranking_report_file_saved(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _insert_cycle(database, db_id=1, opened_at="2026-07-02T10:00:00", closed_at="2026-07-02T10:01:00")
    database.save_hf_market_snapshot(_snapshot("2026-07-02T10:00:00", price=1.00000000))
    database.save_hf_market_snapshot(_snapshot("2026-07-02T10:01:00", price=0.99992000))
    output = tmp_path / "ranking.txt"

    report = ExtremeReplayRankingEngine(database).build_report(output_path=output)

    assert output.exists()
    assert "Extreme Replay Scenario Ranking" in output.read_text(encoding="utf-8")
    assert report.report_path == str(output)
