import json
from datetime import datetime, timedelta

import pytest

from analytics.hf_real_vs_paper_diagnostics_engine import HFRealVsPaperDiagnosticsEngine
from storage.database_manager import DatabaseManager


PROFILE = "mean_reversion_hf_micro_v1"


def _snapshot(database: DatabaseManager, timestamp: datetime, price: float, *, bid: float | None = None, ask: float | None = None, distance_to_short_center: float = -0.00001) -> None:
    bid = price - 0.000005 if bid is None else bid
    ask = price + 0.000005 if ask is None else ask
    database.save_hf_market_snapshot({
        "timestamp": timestamp.isoformat(),
        "symbol": "USDCUSDT",
        "price": price,
        "bid": bid,
        "ask": ask,
        "mid_price": price,
        "spread": ask - bid,
        "work_position": 50.0,
        "micro_trend": "NEUTRAL",
        "entry_zone": "CENTER",
        "buy_zone": False,
        "sell_zone": False,
        "volatility_regime": "NORMAL",
        "market_regime": "NORMAL",
        "distance_to_long_center": 0.0,
        "distance_to_short_center": distance_to_short_center,
        "distance_to_work_center": 0.0,
        "order_book_pressure": "UNKNOWN",
        "session": "NEW_YORK",
        "price_change_5_sec": 0.0,
        "price_change_10_sec": 0.0,
        "price_change_30_sec": 0.0,
        "price_change_1_min": 0.0,
        "price_change_5_min": 0.0,
        "would_open_cycle": True,
        "reason_if_not": "N/A",
        "data_source": "TEST",
    })


def _real_cycle(
    database: DatabaseManager,
    *,
    db_id: int = 1,
    direction: str = "BUY_USDC",
    open_price: float = 1.0,
    close_price: float = 1.000005,
    quantity: float = 10.0,
    net_profit: float = 0.00005,
    close_reason: str = "real_pilot_target",
    opened_at: datetime | None = None,
    closed_at: datetime | None = None,
    run_id: str = "run-1",
) -> None:
    opened_at = opened_at or datetime(2026, 7, 8, 12, 0, 0)
    closed_at = closed_at or opened_at + timedelta(seconds=60)
    with database.connect() as conn:
        conn.execute(
            """
            INSERT INTO real_pilot_cycles (
                id, timestamp, strategy_profile, symbol, direction, status,
                open_price, close_price, quantity, stake_usdt, gross_profit,
                net_profit, opened_at, closed_at, close_reason, exchange_order_id, run_id
            ) VALUES (?, ?, ?, 'USDCUSDT', ?, 'CLOSED', ?, ?, ?, 6, ?, ?, ?, ?, ?, 'entry-order', ?)
            """,
            (
                db_id,
                opened_at.isoformat(),
                PROFILE,
                direction,
                open_price,
                close_price,
                quantity,
                net_profit,
                net_profit,
                opened_at.isoformat(),
                closed_at.isoformat(),
                close_reason,
                run_id,
            ),
        )
        conn.commit()


def _order_event(database: DatabaseManager, *, run_id: str = "run-1", side: str = "BUY", close_cycle_id: int | None = None) -> None:
    request = {"symbol": "USDCUSDT", "side": side, "type": "MARKET", "quantity": "10"}
    if close_cycle_id is not None:
        request["close_cycle_id"] = close_cycle_id
    response = {
        "orderId": "mock",
        "status": "FILLED",
        "executedQty": "10",
        "cummulativeQuoteQty": "10.00005",
        "fills": [{"price": "1.000005", "qty": "10", "commission": "0.000001"}],
    }
    database.save_real_pilot_order_event(
        run_id=run_id,
        strategy_profile=PROFILE,
        symbol="USDCUSDT",
        side=side,
        quantity=10,
        status="FILLED",
        request_payload=json.dumps(request),
        response_payload=json.dumps(response),
    )


def test_real_vs_paper_handles_empty_real_cycles(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    report = HFRealVsPaperDiagnosticsEngine(database).build_report(PROFILE)

    assert report.total_real_cycles == 0
    assert report.cycles == []
    assert report.main_suspected_issue == "unknown"


def test_real_vs_paper_detects_target_touched_and_path(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    start = datetime(2026, 7, 8, 12, 0, 0)
    _real_cycle(database, opened_at=start, closed_at=start + timedelta(seconds=60))
    _snapshot(database, start, 1.0)
    _snapshot(database, start + timedelta(seconds=5), 1.000002)
    _snapshot(database, start + timedelta(seconds=15), 1.000006)
    _order_event(database)
    _order_event(database, side="SELL", close_cycle_id=1)

    report = HFRealVsPaperDiagnosticsEngine(database).build_report(PROFILE)

    cycle = report.cycles[0]
    assert cycle.target_touched is True
    assert cycle.price_after_5s == pytest.approx(1.000002)
    assert cycle.max_favorable_excursion == pytest.approx(0.000006)
    assert cycle.paper_target_hit is True
    assert cycle.paper_equivalent_net > 0
    assert cycle.filled_quantity == pytest.approx(10)
    assert cycle.commission == pytest.approx(0.000002)


def test_real_vs_paper_categorizes_timeout_cycle(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    start = datetime(2026, 7, 8, 12, 0, 0)
    _real_cycle(
        database,
        open_price=1.0,
        close_price=0.99999,
        net_profit=-0.0001,
        close_reason="max_holding_270s",
        opened_at=start,
        closed_at=start + timedelta(seconds=270),
    )
    _snapshot(database, start, 1.0)
    _snapshot(database, start + timedelta(seconds=270), 0.99999)

    report = HFRealVsPaperDiagnosticsEngine(database).build_report(PROFILE)

    assert report.timeout_closes == 1
    assert report.timeout_loss_count == 1
    assert report.cycles[0].paper_timeout is True


def test_real_vs_paper_paper_equivalent_comparison_with_mocked_data(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    start = datetime(2026, 7, 8, 12, 0, 0)
    _real_cycle(database, open_price=1.0, close_price=0.99999, net_profit=-0.0001, opened_at=start)
    _snapshot(database, start, 1.0)
    _snapshot(database, start + timedelta(seconds=30), 1.000006)

    report = HFRealVsPaperDiagnosticsEngine(database).build_report(PROFILE)

    assert report.estimated_paper_equivalent_net > 0
    assert report.real_minus_paper_delta < 0


def test_real_vs_paper_execution_events_parsed_correctly(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    _real_cycle(database)
    _order_event(database)
    _order_event(database, side="SELL", close_cycle_id=1)

    report = HFRealVsPaperDiagnosticsEngine(database).build_report(PROFILE)

    cycle = report.cycles[0]
    assert cycle.quote_amount == pytest.approx(10.00005)
    assert cycle.maker_taker_role == "TAKER"


def test_real_vs_paper_uses_blackbox_snapshots_when_available(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    start = datetime(2026, 7, 8, 12, 0, 0)
    _real_cycle(
        database,
        open_price=1.0,
        close_price=0.99999,
        net_profit=-0.0001,
        close_reason="max_holding_270s",
        opened_at=start,
        closed_at=start + timedelta(seconds=270),
    )
    database.save_real_pilot_market_snapshot(
        real_cycle_id=1,
        campaign_id="campaign-1",
        timestamp=start.isoformat(),
        phase="entry",
        symbol="USDCUSDT",
        price=1.0,
        bid=0.999995,
        ask=1.000005,
        mid=1.0,
        spread=0.00001,
        short_center=1.00001,
        hf_entry_mode="short_center",
        candidate=True,
        block_reason="N/A",
        direction="BUY_USDC",
        target_price=1.000005,
        distance_to_target=0.000005,
        unrealized_pnl=0.0,
        open_real_cycles=1,
        source="TEST",
    )
    database.save_real_pilot_market_snapshot(
        real_cycle_id=1,
        campaign_id="campaign-1",
        timestamp=(start + timedelta(seconds=15)).isoformat(),
        phase="tracking",
        symbol="USDCUSDT",
        price=1.000006,
        bid=1.000001,
        ask=1.000011,
        mid=1.000006,
        spread=0.00001,
        short_center=1.00001,
        hf_entry_mode="short_center",
        candidate=True,
        block_reason="N/A",
        direction="BUY_USDC",
        target_price=1.000005,
        distance_to_target=-0.000001,
        unrealized_pnl=0.00006,
        open_real_cycles=1,
        source="TEST",
    )

    report = HFRealVsPaperDiagnosticsEngine(database).build_report(PROFILE)

    assert report.cycles[0].target_touched is True
    assert report.cycles[0].paper_target_hit is True
    assert report.cycles[0].paper_equivalent_net > 0


def test_real_vs_paper_distinguishes_touch_semantics_for_timeout_cycle(tmp_path):
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))
    start = datetime(2026, 7, 20, 18, 20, 16)
    _real_cycle(
        database,
        db_id=25,
        open_price=1.00068,
        close_price=1.00064,
        quantity=5,
        net_profit=-0.0002,
        close_reason="max_holding_270s",
        opened_at=start,
        closed_at=start + timedelta(seconds=270),
        run_id="run-25",
    )
    database.save_real_pilot_market_snapshot(
        real_cycle_id=25,
        campaign_id="campaign-25",
        timestamp=(start + timedelta(milliseconds=24)).isoformat(),
        phase="entry",
        symbol="USDCUSDT",
        price=1.000695,
        bid=1.000690,
        ask=1.000700,
        mid=1.000695,
        spread=0.00001,
        short_center=1.000715,
        hf_entry_mode="short_center",
        candidate=True,
        block_reason="N/A",
        direction="BUY_USDC",
        target_price=1.0006850034,
        distance_to_target=None,
        unrealized_pnl=None,
        open_real_cycles=1,
        source="TEST",
    )
    database.save_real_pilot_market_snapshot(
        real_cycle_id=25,
        campaign_id="campaign-25",
        timestamp=(start + timedelta(seconds=270)).isoformat(),
        phase="exit",
        symbol="USDCUSDT",
        price=1.000640,
        bid=1.000640,
        ask=1.000650,
        mid=1.000645,
        spread=0.00001,
        short_center=None,
        hf_entry_mode=None,
        candidate=None,
        block_reason=None,
        direction="BUY_USDC",
        target_price=1.0006850034,
        distance_to_target=0.0000450034,
        unrealized_pnl=-0.0002,
        open_real_cycles=1,
        source="TEST",
    )

    report = HFRealVsPaperDiagnosticsEngine(database).build_report(PROFILE)
    cycle = report.cycles[0]

    assert cycle.reference_target_touched is True
    assert cycle.executable_target_touched is True
    assert cycle.real_target_close_triggered is False
    assert cycle.target_close_order_sent is False
    assert cycle.target_close_order_filled is False
    assert cycle.close_reason == "max_holding_270s"
