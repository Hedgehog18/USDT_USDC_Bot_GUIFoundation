from types import SimpleNamespace

from paper.paper_analytics_engine import PaperAnalytics
from paper.paper_trading_cli_renderer import PaperTradingCliRenderer


def _stats() -> PaperAnalytics:
    return PaperAnalytics(
        total_cycles=5,
        closed_cycles=4,
        winning_cycles=2,
        losing_cycles=1,
        win_rate=0.5,
        gross_profit=0.01,
        net_profit=0.02,
        average_net_profit=0.005,
        profit_factor=2.0,
        breakeven_cycles=1,
        average_profit=0.02,
        average_loss=-0.01,
        average_cycle_pnl=0.005,
        expectancy=0.005,
        timeout_closed=2,
        timeout_profit_cycles=1,
        timeout_breakeven_cycles=0,
        timeout_loss_cycles=1,
        timeout_average_pnl=-0.001,
        timeout_max_profit=0.003,
        timeout_max_loss=-0.005,
        target_closed=2,
        target_total_profit=0.03,
        target_average_profit=0.015,
        buy_count=2,
        buy_total_pnl=0.01,
        buy_average_pnl=0.005,
        buy_win_rate=0.5,
        sell_count=2,
        sell_total_pnl=0.01,
        sell_average_pnl=0.005,
        sell_win_rate=0.5,
    )


def test_renderer_prints_paper_stats_without_rich(capsys):
    PaperTradingCliRenderer(force_plain=True).render_paper_stats(_stats())

    output = capsys.readouterr().out

    assert "PAPER TRADING STATS" in output
    assert "Net Profit: +0.02000000" in output
    assert "Timeout Profit: 1" in output
    assert "BUY Win Rate: 50.00%" in output


def test_renderer_hides_na_collection_fields(capsys):
    stats = {
        "closed_cycles": 0,
        "automatic_closed": 0,
        "manual_closed": 0,
        "target_closed": 0,
        "timeout_closed": 0,
        "open_cycles": 0,
        "net_profit": 0.0,
        "win_rate": 0.0,
        "winning_cycles": 0,
        "breakeven_cycles": 0,
        "losing_cycles": 0,
    }
    diagnostics = {
        "candidate_detected": "no",
        "entry_block_reason": "no_signal",
        "short_center": "N/A",
        "short_center_samples": "N/A",
        "hf_entry_mode": "N/A",
        "entry_direction": "N/A",
        "target_price": "N/A",
        "target_distance": "N/A",
        "safety_filter_passed": "N/A",
        "safety_block_reason": "N/A",
    }

    PaperTradingCliRenderer(force_plain=True).render_collection_progress(
        stats,
        5,
        iteration=0,
        price_info=None,
        nearest_open_cycle=None,
        action_taken="waiting",
        close_reason="N/A",
        entry_diagnostics=diagnostics,
        new_mode=True,
    )

    output = capsys.readouterr().out

    assert "NEW CLOSED 0 / 5" in output
    assert "No open cycle" in output
    assert "Entry Block Reason: no_signal" in output
    assert "safety_filter_passed" not in output
    assert "N/A" not in output


def test_renderer_prints_open_cycle(capsys):
    open_cycle = SimpleNamespace(
        db_id=10,
        direction="SELL_USDC",
        current_price=1.0009,
        target_price=1.0008,
        distance_to_target=0.0001,
        unrealized_pnl=-0.0002,
        age_seconds=168,
        close_condition_met=False,
    )
    stats = {
        "closed_cycles": 1,
        "open_cycles": 1,
        "net_profit": 0.001,
        "win_rate": 1.0,
    }
    diagnostics = {
        "candidate_detected": "no",
        "entry_block_reason": "existing_cycle",
        "short_center": "1.00085000",
        "short_center_samples": "60",
        "hf_entry_mode": "short_center",
        "entry_direction": "N/A",
        "target_price": "N/A",
        "target_distance": "N/A",
        "safety_filter_passed": "N/A",
        "safety_block_reason": "N/A",
    }

    PaperTradingCliRenderer(force_plain=True).render_collection_progress(
        stats,
        5,
        iteration=2,
        price_info=(1.0009, "BINANCE", "2026-07-01T10:00:00"),
        nearest_open_cycle=open_cycle,
        action_taken="waiting",
        close_reason="N/A",
        entry_diagnostics=diagnostics,
    )

    output = capsys.readouterr().out

    assert "CURRENT CYCLE" in output
    assert "Direction: SELL_USDC" in output
    assert "Unrealized PnL: -0.00020000" in output
    assert "Age: 168s" in output


def test_renderer_prints_collection_summary(capsys):
    stats = {
        "closed_cycles": 5,
        "automatic_closed": 5,
        "target_closed": 3,
        "timeout_closed": 2,
        "timeout_profit": 1,
        "timeout_breakeven": 0,
        "timeout_loss": 1,
        "manual_closed": 0,
        "net_profit": 0.01,
        "win_rate": 0.6,
    }

    PaperTradingCliRenderer(force_plain=True).render_collection_summary(stats)

    output = capsys.readouterr().out

    assert "NEW COLLECTION SUMMARY" in output
    assert "Timeout Profit: 1" in output
    assert "Win Rate: 60.00%" in output
