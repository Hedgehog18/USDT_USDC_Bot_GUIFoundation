from pathlib import Path

from analytics.hf_micro_grid_sim_engine import HFMicroGridSimulationEngine
from analytics.micro_cycle_sim_engine import MicroCycleSimulationEngine
from storage.database_manager import DatabaseManager


def _snapshot(**overrides) -> dict:
    price = overrides.pop("price", 1.0)
    short_center = overrides.pop("short_center", price + 0.0001)
    base = {
        "timestamp": "2026-06-26T13:00:00",
        "symbol": "USDCUSDT",
        "price": price,
        "bid": price - 0.00001,
        "ask": price + 0.00001,
        "mid_price": price,
        "spread": 0.00001,
        "work_position": 50.0,
        "micro_trend": "NEUTRAL",
        "entry_zone": "NONE",
        "buy_zone": False,
        "sell_zone": False,
        "volatility_regime": "LOW",
        "market_regime": "NORMAL",
        "distance_to_long_center": 0.0,
        "distance_to_short_center": price - short_center,
        "distance_to_work_center": 0.0,
        "order_book_pressure": "BALANCED",
        "session": "LONDON_NEW_YORK_OVERLAP",
        "price_change_5_sec": 0.0,
        "price_change_10_sec": 0.0,
        "price_change_30_sec": 0.0,
        "price_change_1_min": 0.0,
        "price_change_5_min": 0.0,
        "would_open_cycle": True,
        "reason_if_not": "",
        "data_source": "TEST",
    }
    base.update(overrides)
    return base


def _database_with_snapshots(tmp_path: Path, snapshots: list[dict]) -> DatabaseManager:
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    for snapshot in snapshots:
        database.save_hf_market_snapshot(snapshot)
    return database


def _simulate(test_config, tmp_path: Path, snapshots: list[dict], **overrides):
    database = _database_with_snapshots(tmp_path, snapshots)
    rows = MicroCycleSimulationEngine(database, test_config)._load_rows()
    return HFMicroGridSimulationEngine(database, test_config).simulate(
        rows=rows,
        scenario=overrides.pop("scenario", "short_term_mean_reversion"),
        target_percent=overrides.pop("target_percent", 0.001),
        max_holding_seconds=overrides.pop("max_holding_seconds", 270),
        layer_size=overrides.pop("layer_size", 10),
        max_layers=overrides.pop("max_layers", 10),
        baseline=None,
    )


def test_hf_micro_grid_sim_empty_dataset(test_config, tmp_path: Path) -> None:
    report = _simulate(test_config, tmp_path, [])

    assert report.total_samples == 0
    assert report.opened_layers == 0
    assert report.max_total_equity_drawdown == 0.0
    assert report.final_active_layers == 0
    assert report.drawdown_diagnostics.events == []
    assert report.recommendation == "NOT WORTH TESTING"


def test_hf_micro_grid_sim_opens_one_layer(test_config, tmp_path: Path) -> None:
    report = _simulate(test_config, tmp_path, [
        _snapshot(timestamp="2026-06-26T13:00:00", price=1.0),
    ])

    assert report.opened_layers == 1
    assert report.active_layers == 1
    assert report.maximum_simultaneous_layers == 1


def test_hf_micro_grid_sim_opens_second_layer_after_270_seconds(test_config, tmp_path: Path) -> None:
    report = _simulate(test_config, tmp_path, [
        _snapshot(timestamp="2026-06-26T13:00:00", price=1.0),
        _snapshot(timestamp="2026-06-26T13:04:29", price=0.9999),
        _snapshot(timestamp="2026-06-26T13:04:30", price=0.9998),
    ])

    assert report.opened_layers == 2
    assert report.active_layers == 2
    assert report.maximum_simultaneous_layers == 2
    assert report.skipped_opportunities_spacing == 1


def test_hf_micro_grid_sim_caps_at_max_10_layers(test_config, tmp_path: Path) -> None:
    snapshots = [
        _snapshot(
            timestamp=f"2026-06-26T13:{minute:02d}:00",
            price=1.0 - index * 0.0001,
        )
        for index, minute in enumerate(range(0, 55, 5))
    ]

    report = _simulate(test_config, tmp_path, snapshots, max_holding_seconds=270, max_layers=10)

    assert report.opened_layers == 10
    assert report.active_layers == 10
    assert report.maximum_simultaneous_layers == 10
    assert report.skipped_opportunities_no_layer == 1
    assert report.all_layers_occupied_count == 1


def test_hf_micro_grid_sim_layer_closes_independently(test_config, tmp_path: Path) -> None:
    report = _simulate(test_config, tmp_path, [
        _snapshot(timestamp="2026-06-26T13:00:00", price=1.0),
        _snapshot(timestamp="2026-06-26T13:00:05", price=1.00002, short_center=1.00012),
    ])

    assert report.opened_layers == 1
    assert report.closed_layers == 1
    assert report.active_layers == 0
    assert report.target_closes == 1
    assert report.closed_layer_details[0].close_reason == "target"


def test_hf_micro_grid_sim_capital_and_occupancy_calculated(test_config, tmp_path: Path) -> None:
    report = _simulate(test_config, tmp_path, [
        _snapshot(timestamp="2026-06-26T13:00:00", price=1.0),
        _snapshot(timestamp="2026-06-26T13:04:30", price=0.9999),
        _snapshot(timestamp="2026-06-26T13:09:00", price=0.9998),
    ])

    assert report.average_occupied_layers == 2.0
    assert report.average_capital_used == 20.0
    assert report.maximum_capital_used == 30.0
    assert report.occupancy_histogram[1] == 1
    assert report.occupancy_histogram[2] == 1
    assert report.occupancy_histogram[3] == 1


def test_hf_micro_grid_sim_timeout_win_close(test_config, tmp_path: Path) -> None:
    report = _simulate(
        test_config,
        tmp_path,
        [
            _snapshot(timestamp="2026-06-26T13:00:00", price=1.0),
            _snapshot(timestamp="2026-06-26T13:04:30", price=1.000005, short_center=1.000105),
        ],
        target_percent=0.001,
    )

    assert report.timeout_closes == 1
    assert report.timeout_wins == 1
    assert report.timeout_losses == 0


def test_hf_micro_grid_sim_comparison_with_hf_v1(test_config, tmp_path: Path) -> None:
    database = _database_with_snapshots(tmp_path, [
        _snapshot(timestamp="2026-06-26T13:00:00", price=1.0),
        _snapshot(timestamp="2026-06-26T13:00:05", price=1.00002, short_center=1.00012),
    ])

    report = HFMicroGridSimulationEngine(database, test_config).build_report()

    assert report.comparison.baseline_cycles_per_day > 0
    assert report.comparison.verdict in {"BETTER", "SIMILAR", "WORSE"}


def test_hf_micro_grid_sim_unrealized_pnl_for_buy_layer(test_config, tmp_path: Path) -> None:
    report = _simulate(test_config, tmp_path, [
        _snapshot(timestamp="2026-06-26T13:00:00", price=1.0),
        _snapshot(timestamp="2026-06-26T13:01:00", price=0.9999),
    ])

    assert report.worst_single_layer_unrealized_loss < 0
    assert report.worst_open_basket_loss < 0
    assert report.final_unrealized_pnl < 0


def test_hf_micro_grid_sim_unrealized_pnl_for_sell_layer(test_config, tmp_path: Path) -> None:
    report = _simulate(test_config, tmp_path, [
        _snapshot(timestamp="2026-06-26T13:00:00", price=1.0, short_center=0.9999),
        _snapshot(timestamp="2026-06-26T13:01:00", price=1.0001, short_center=1.0),
    ])

    assert report.worst_single_layer_unrealized_loss < 0
    assert report.worst_open_basket_loss < 0
    assert report.final_unrealized_pnl < 0


def test_hf_micro_grid_sim_total_equity_drawdown_includes_unrealized(test_config, tmp_path: Path) -> None:
    report = _simulate(test_config, tmp_path, [
        _snapshot(timestamp="2026-06-26T13:00:00", price=1.0),
        _snapshot(timestamp="2026-06-26T13:01:00", price=0.9999),
    ])

    assert report.max_realized_drawdown == 0.0
    assert report.max_total_equity_drawdown < 0
    assert report.max_total_equity_drawdown == report.worst_open_basket_loss


def test_hf_micro_grid_sim_worst_basket_snapshot_and_final_active_layers(test_config, tmp_path: Path) -> None:
    report = _simulate(test_config, tmp_path, [
        _snapshot(timestamp="2026-06-26T13:00:00", price=1.0),
        _snapshot(timestamp="2026-06-26T13:04:30", price=0.9999),
    ])

    assert report.final_active_layers == 2
    assert report.final_capital_locked == 20.0
    assert report.final_total_equity_pnl == report.final_unrealized_pnl
    assert report.worst_basket_snapshot is not None
    assert report.worst_basket_snapshot.active_layers_count == 2
    assert report.worst_basket_snapshot.unrealized_pnl < 0


def test_hf_micro_grid_sim_recommendation_downgrades_when_drawdown_too_high(test_config, tmp_path: Path) -> None:
    snapshots = [
        _snapshot(
            timestamp=f"2026-06-26T13:{minute:02d}:00",
            price=1.0 - index * 0.001,
        )
        for index, minute in enumerate(range(0, 55, 5))
    ]

    report = _simulate(test_config, tmp_path, snapshots, max_holding_seconds=270, max_layers=10)

    assert report.max_total_equity_drawdown < -0.01
    assert report.recommendation != "STRONG PAPER CANDIDATE"


def test_hf_micro_grid_sim_collects_drawdown_events(test_config, tmp_path: Path) -> None:
    report = _simulate(test_config, tmp_path, [
        _snapshot(timestamp="2026-06-26T13:00:00", price=1.0),
        _snapshot(timestamp="2026-06-26T13:04:30", price=0.9999),
    ])

    events = report.drawdown_diagnostics.events

    assert events
    assert events[0].total_equity_pnl < 0
    assert events[0].active_layers_count == 2


def test_hf_micro_grid_sim_worst_drawdown_events_sorted(test_config, tmp_path: Path) -> None:
    report = _simulate(test_config, tmp_path, [
        _snapshot(timestamp="2026-06-26T13:00:00", price=1.0),
        _snapshot(timestamp="2026-06-26T13:04:30", price=0.99995),
        _snapshot(timestamp="2026-06-26T13:09:00", price=0.9998),
    ])

    values = [event.total_equity_drawdown for event in report.drawdown_diagnostics.events]

    assert values == sorted(values)


def test_hf_micro_grid_sim_dominant_direction_calculated(test_config, tmp_path: Path) -> None:
    report = _simulate(test_config, tmp_path, [
        _snapshot(timestamp="2026-06-26T13:00:00", price=1.0),
        _snapshot(timestamp="2026-06-26T13:04:30", price=0.9999),
    ])

    event = report.drawdown_diagnostics.events[0]

    assert event.dominant_direction == "BUY"
    assert event.buy_layers_count == 2
    assert event.sell_layers_count == 0


def test_hf_micro_grid_sim_layer_age_diagnostics_calculated(test_config, tmp_path: Path) -> None:
    report = _simulate(test_config, tmp_path, [
        _snapshot(timestamp="2026-06-26T13:00:00", price=1.0),
        _snapshot(timestamp="2026-06-26T13:04:30", price=0.9999),
    ])

    event = report.drawdown_diagnostics.events[0]

    assert len(event.layer_ages_seconds) == 2
    assert event.oldest_layer_age_seconds == 270.0
    assert event.newest_layer_age_seconds == 0.0


def test_hf_micro_grid_sim_drawdown_aggregates_and_recommendations(test_config, tmp_path: Path) -> None:
    snapshots = [
        _snapshot(
            timestamp=f"2026-06-26T13:{minute:02d}:00",
            price=1.0 - index * 0.001,
        )
        for index, minute in enumerate(range(0, 55, 5))
    ]

    report = _simulate(test_config, tmp_path, snapshots, max_holding_seconds=270, max_layers=10)
    diagnostics = report.drawdown_diagnostics

    assert diagnostics.by_active_layer_count
    assert diagnostics.by_dominant_direction
    assert diagnostics.layer_additions_count == report.opened_layers
    assert "add basket stop" in diagnostics.recommendations
