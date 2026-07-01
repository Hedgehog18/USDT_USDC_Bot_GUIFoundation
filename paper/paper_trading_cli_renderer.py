from __future__ import annotations

from typing import Any

try:
    from rich.console import Console, Group
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
except Exception:  # pragma: no cover - exercised through force_plain tests.
    Console = None
    Group = None
    Panel = None
    Table = None
    Text = None


class PaperTradingCliRenderer:
    def __init__(self, *, force_plain: bool = False) -> None:
        self._rich_enabled = not force_plain and Console is not None
        self._console = Console() if self._rich_enabled else None

    def render_paper_stats(self, stats, *, title: str = "PAPER TRADING STATS") -> None:
        sections = [
            self._section(title, [
                ("Total cycles", stats.total_cycles),
                ("Closed cycles", stats.closed_cycles),
                ("Profitable", stats.winning_cycles),
                ("Breakeven", stats.breakeven_cycles),
                ("Losing", stats.losing_cycles),
            ]),
            self._section("PERFORMANCE", [
                ("Net Profit", self._format_signed(stats.net_profit)),
                ("Win Rate", self._format_percent(stats.win_rate)),
                ("Avg Profit", self._format_float(stats.average_profit)),
                ("Avg Loss", self._format_float(stats.average_loss)),
                ("Avg Cycle PnL", self._format_float(stats.average_cycle_pnl)),
                ("Expectancy", self._format_float(stats.expectancy)),
                ("Profit Factor", f"{stats.profit_factor:.4f}"),
            ]),
            self._section("CLOSE BREAKDOWN", [
                ("Target", stats.target_closed),
                ("Target Total", self._format_signed(stats.target_total_profit)),
                ("Target Avg", self._format_float(stats.target_average_profit)),
                ("Timeout", stats.timeout_closed),
                ("Timeout Profit", stats.timeout_profit_cycles),
                ("Timeout Breakeven", stats.timeout_breakeven_cycles),
                ("Timeout Loss", stats.timeout_loss_cycles),
                ("Timeout Avg PnL", self._format_float(stats.timeout_average_pnl)),
            ]),
            self._section("DIRECTION BREAKDOWN", [
                ("BUY Count", stats.buy_count),
                ("BUY PnL", self._format_signed(stats.buy_total_pnl)),
                ("BUY Avg", self._format_float(stats.buy_average_pnl)),
                ("BUY Win Rate", self._format_percent(stats.buy_win_rate)),
                ("SELL Count", stats.sell_count),
                ("SELL PnL", self._format_signed(stats.sell_total_pnl)),
                ("SELL Avg", self._format_float(stats.sell_average_pnl)),
                ("SELL Win Rate", self._format_percent(stats.sell_win_rate)),
            ]),
        ]
        self._render_sections(sections)

    def render_paper_cycle_sim(self, result, stats, insights, *, profile: str, summary_path: Any, insights_path: Any) -> None:
        sections = [
            self._section("PAPER CYCLE SIM", [
                ("Profile", profile),
                ("Iterations", result.iterations),
                ("Opened", result.opened_cycles),
                ("Closed", result.closed_cycles),
                ("Safety stops", result.safety_stops),
                ("Final USDT", self._format_float(result.final_portfolio.usdt)),
                ("Final USDC", self._format_float(result.final_portfolio.usdc)),
                ("Final value", self._format_float(result.final_portfolio.total_value)),
            ]),
            self._section("PERFORMANCE", [
                ("Net Profit", self._format_signed(stats.net_profit)),
                ("Win Rate", self._format_percent(stats.win_rate)),
                ("Avg Cycle PnL", self._format_float(stats.average_cycle_pnl)),
                ("Expectancy", self._format_float(stats.expectancy)),
                ("Profit Factor", f"{stats.profit_factor:.4f}"),
            ]),
            self._section("CLOSE BREAKDOWN", [
                ("Target", stats.target_closed),
                ("Timeout", stats.timeout_closed),
                ("Timeout Profit", stats.timeout_profit_cycles),
                ("Timeout Breakeven", stats.timeout_breakeven_cycles),
                ("Timeout Loss", stats.timeout_loss_cycles),
            ]),
            self._section("PAPER INSIGHTS", [
                ("Rating", insights.rating),
                ("Summary", insights.summary),
                ("Summary CSV", summary_path),
                ("Insights TXT", insights_path),
            ]),
        ]
        self._render_sections(sections)

    def render_collection_progress(
        self,
        stats: dict[str, float | int],
        target: int,
        *,
        iteration: int,
        price_info: tuple[float, str, str] | None,
        nearest_open_cycle,
        action_taken: str,
        close_reason: str,
        entry_diagnostics: dict[str, str],
        new_mode: bool = False,
    ) -> None:
        current_price, data_source, price_timestamp = price_info if price_info else (None, "N/A", "N/A")
        closed_label = "NEW CLOSED" if new_mode else "CLOSED"
        sections = [
            self._section("PAPER TRADING STATUS", [
                ("Collection", iteration),
                ("Progress", f"{closed_label} {int(stats['closed_cycles'])} / {target}"),
                ("Open", int(stats["open_cycles"])),
                ("Action", action_taken),
                ("Close reason", close_reason),
            ]),
            self._section("PERFORMANCE", [
                ("Net Profit", self._format_signed(float(stats["net_profit"]))),
                ("Win Rate", self._format_percent(float(stats["win_rate"]))),
                ("Profitable", int(stats.get("winning_cycles", 0))),
                ("Breakeven", int(stats.get("breakeven_cycles", 0))),
                ("Losing", int(stats.get("losing_cycles", 0))),
            ]),
            self._section("CLOSE BREAKDOWN", [
                ("Automatic", int(stats.get("automatic_closed", 0))),
                ("Target", int(stats.get("target_closed", 0))),
                ("Timeout", int(stats.get("timeout_closed", 0))),
                ("Timeout Profit", int(stats.get("timeout_profit", 0))),
                ("Timeout Breakeven", int(stats.get("timeout_breakeven", 0))),
                ("Timeout Loss", int(stats.get("timeout_loss", 0))),
                ("Manual", int(stats.get("manual_closed", 0))),
            ]),
            self._current_cycle_section(nearest_open_cycle),
            self._market_signal_section(
                current_price=current_price,
                data_source=data_source,
                price_timestamp=price_timestamp,
                entry_diagnostics=entry_diagnostics,
            ),
        ]
        safety = self._safety_section(entry_diagnostics)
        if safety is not None:
            sections.append(safety)
        self._render_sections(sections)

    def render_collection_summary(self, stats: dict[str, float | int]) -> None:
        self._render_sections([
            self._section("NEW COLLECTION SUMMARY", [
                ("Closed", int(stats["closed_cycles"])),
                ("Automatic", int(stats["automatic_closed"])),
                ("Target", int(stats["target_closed"])),
                ("Timeout", int(stats["timeout_closed"])),
                ("Timeout Profit", int(stats.get("timeout_profit", 0))),
                ("Timeout Breakeven", int(stats.get("timeout_breakeven", 0))),
                ("Timeout Loss", int(stats.get("timeout_loss", 0))),
                ("Manual", int(stats["manual_closed"])),
                ("Net Profit", self._format_signed(float(stats["net_profit"]))),
                ("Win Rate", self._format_percent(float(stats["win_rate"]))),
            ])
        ])

    def render_profile_performance_summary(self, summary) -> None:
        sections = [
            self._section("PROFILE PERFORMANCE SUMMARY", [
                ("Profile", summary.profile),
                ("Total cycles", summary.total_profile_cycles),
                ("Automatic closed", summary.automatic_closed_count),
                ("Manual closed", summary.manual_closed_count),
                ("Open", summary.open_count),
                ("Recommendation", summary.recommendation),
            ]),
            self._section("PERFORMANCE", [
                ("Realized Net", self._format_signed(summary.total_realized_net_profit)),
                ("Automatic Net", self._format_signed(summary.automatic_closed_net_profit)),
                ("Manual Net", self._format_signed(summary.manual_closed_net_profit)),
                ("Win Rate", self._format_percent(summary.real_outcome_win_rate)),
                ("Avg Cycle PnL", self._format_float(summary.average_cycle_pnl)),
                ("Expectancy", self._format_float(summary.expectancy)),
                ("Profit Factor", f"{summary.profit_factor:.4f}"),
            ]),
            self._section("CLOSE BREAKDOWN", [
                ("Target", summary.target_closed_count),
                ("Target Total", self._format_signed(summary.target_total_profit)),
                ("Timeout", summary.timeout_closed_count),
                ("Timeout Profit", summary.timeout_profit_count),
                ("Timeout Breakeven", summary.timeout_breakeven_count),
                ("Timeout Loss", summary.timeout_loss_count),
                ("Manual close rate", self._format_percent(summary.manual_close_rate)),
                ("Stale", summary.stale_close_count),
            ]),
            self._section("DIRECTION BREAKDOWN", [
                ("BUY Count", summary.buy_breakdown.total_cycles),
                ("BUY Net", self._format_signed(summary.buy_breakdown.net_profit)),
                ("BUY Win Rate", self._format_percent(summary.buy_breakdown.win_rate)),
                ("SELL Count", summary.sell_breakdown.total_cycles),
                ("SELL Net", self._format_signed(summary.sell_breakdown.net_profit)),
                ("SELL Win Rate", self._format_percent(summary.sell_breakdown.win_rate)),
            ]),
        ]
        self._render_sections(sections)

    def _current_cycle_section(self, nearest_open_cycle):
        if nearest_open_cycle is None:
            return self._section("CURRENT CYCLE", [("Status", "No open cycle")])
        return self._section("CURRENT CYCLE", [
            ("DB ID", getattr(nearest_open_cycle, "db_id", "N/A")),
            ("Direction", getattr(nearest_open_cycle, "direction", "N/A")),
            ("Current Price", self._format_float(getattr(nearest_open_cycle, "current_price", None))),
            ("Target Price", self._format_float(getattr(nearest_open_cycle, "target_price", None))),
            ("Distance", self._format_float(getattr(nearest_open_cycle, "distance_to_target", None))),
            ("Unrealized PnL", self._format_signed(getattr(nearest_open_cycle, "unrealized_pnl", 0.0))),
            ("Age", self._format_seconds(getattr(nearest_open_cycle, "age_seconds", None))),
            ("Close Ready", "yes" if getattr(nearest_open_cycle, "close_condition_met", False) else "no"),
        ])

    def _market_signal_section(
        self,
        *,
        current_price: float | None,
        data_source: str,
        price_timestamp: str,
        entry_diagnostics: dict[str, str],
    ):
        return self._section("MARKET / SIGNAL", [
            ("Price", self._format_float(current_price)),
            ("Source", data_source),
            ("Timestamp", price_timestamp),
            ("Short Center", entry_diagnostics.get("short_center")),
            ("Center Samples", entry_diagnostics.get("short_center_samples")),
            ("Entry Mode", entry_diagnostics.get("hf_entry_mode")),
            ("Candidate", entry_diagnostics.get("candidate_detected")),
            ("Entry Direction", entry_diagnostics.get("entry_direction")),
            ("Entry Block Reason", entry_diagnostics.get("entry_block_reason")),
            ("Target Price", entry_diagnostics.get("target_price")),
            ("Target Distance", entry_diagnostics.get("target_distance")),
        ])

    def _safety_section(self, entry_diagnostics: dict[str, str]):
        reason = entry_diagnostics.get("safety_block_reason", "N/A")
        passed = entry_diagnostics.get("safety_filter_passed", "N/A")
        should_show = passed == "no" or self._is_useful(reason)
        if not should_show:
            return None
        return self._section("SAFETY / WARNING", [
            ("Safety Passed", passed),
            ("Block Reason", reason),
            ("Details", entry_diagnostics.get("safety_block_details")),
            ("Safety State", entry_diagnostics.get("paper_safety_state")),
            ("Policy", entry_diagnostics.get("paper_safety_policy")),
            ("Consecutive Losses", entry_diagnostics.get("safety_consecutive_losses")),
            ("Realized Drawdown", entry_diagnostics.get("safety_realized_drawdown")),
            ("Timeout Loss Rate", entry_diagnostics.get("safety_timeout_loss_rate")),
        ])

    def _section(self, title: str, rows: list[tuple[str, Any]]):
        filtered = [(label, value) for label, value in rows if self._is_useful(value)]
        if self._rich_enabled:
            table = Table.grid(padding=(0, 2))
            table.add_column(style="bold")
            table.add_column()
            for label, value in filtered:
                table.add_row(f"{label}:", self._styled_value(value))
            return Panel(table, title=title, border_style="cyan")
        return (title, filtered)

    def _render_sections(self, sections: list[Any]) -> None:
        if self._rich_enabled:
            self._console.print(Group(*sections))
            return
        for title, rows in sections:
            print(f"=== {title} ===")
            for label, value in rows:
                print(f"{label}: {value}")

    def _styled_value(self, value: Any):
        text = str(value)
        style = ""
        lowered = text.lower()
        if text.startswith("+") or lowered in {"success", "closed", "yes"}:
            style = "green"
        elif text.startswith("-") or lowered in {"error", "no"}:
            style = "red"
        elif lowered in {"warning", "waiting", "blocked"} or "loss" in lowered:
            style = "yellow"
        return Text(text, style=style) if Text is not None else text

    @staticmethod
    def _is_useful(value: Any) -> bool:
        if value is None:
            return False
        return str(value) not in {"", "N/A", "None"}

    @staticmethod
    def _format_float(value: Any) -> str:
        if value is None or str(value) == "N/A":
            return "N/A"
        return f"{float(value):.8f}"

    @staticmethod
    def _format_signed(value: Any) -> str:
        number = float(value)
        return f"{number:+.8f}"

    @staticmethod
    def _format_percent(value: float) -> str:
        return f"{value * 100:.2f}%"

    @staticmethod
    def _format_seconds(value: Any) -> str:
        if value is None or str(value) == "N/A":
            return "N/A"
        return f"{float(value):.0f}s"
