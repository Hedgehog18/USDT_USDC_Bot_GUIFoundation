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
            self._section("EXECUTION QUALITY", [
                ("Missed Target Count", stats.missed_target_count),
                ("Missed Target Then Loss", stats.missed_target_then_loss_count),
                ("Avg Missed PnL", self._format_float(stats.average_missed_pnl)),
                ("Max Adverse PnL", self._format_float(stats.max_adverse_pnl)),
                ("Avg Adverse PnL", self._format_float(stats.average_adverse_pnl)),
                ("Avg Favorable PnL", self._format_float(stats.average_favorable_pnl)),
                ("Worst Close Gap", self._format_float(stats.worst_close_gap_to_target)),
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
        lifetime_stats: dict[str, float | int] | None = None,
        collection_id: str | int | None = None,
        profile: str | None = None,
    ) -> None:
        current_price, data_source, price_timestamp = price_info if price_info else (None, "N/A", "N/A")
        closed_label = "NEW CLOSED" if new_mode else "CLOSED"
        lifetime = lifetime_stats or {}
        sections = [
            self._section("PAPER TRADING STATUS", [
                ("Collection", collection_id if collection_id is not None else iteration),
                ("Profile", profile or "N/A"),
                ("New Closed", f"{int(stats['closed_cycles'])} / {target}"),
                ("Lifetime Closed", int(lifetime.get("closed_cycles", 0))),
                ("Open Cycles", int(stats["open_cycles"])),
                ("Action", action_taken),
                ("Close reason", close_reason),
            ]),
            self._section("CURRENT COLLECTION PERFORMANCE", [
                ("Net Profit", self._format_signed(float(stats["net_profit"]))),
                ("Win Rate", self._format_percent(float(stats["win_rate"]))),
                ("Avg Cycle PnL", self._format_signed(float(stats.get("average_cycle_pnl", 0.0)))),
                ("Expectancy", self._format_signed(float(stats.get("expectancy", 0.0)))),
                ("Profit Factor", f"{float(stats.get('profit_factor', 0.0)):.4f}"),
                ("Profitable", int(stats.get("winning_cycles", 0))),
                ("Breakeven", int(stats.get("breakeven_cycles", 0))),
                ("Losing", int(stats.get("losing_cycles", 0))),
            ]),
            self._section("LIFETIME SUMMARY", [
                ("Closed", int(lifetime.get("closed_cycles", 0))),
                ("Net Profit", self._format_signed(float(lifetime.get("net_profit", 0.0)))),
                ("Win Rate", self._format_percent(float(lifetime.get("win_rate", 0.0)))),
                ("Expectancy", self._format_signed(float(lifetime.get("expectancy", 0.0)))),
                ("Profit Factor", f"{float(lifetime.get('profit_factor', 0.0)):.4f}"),
            ]),
        ]
        if self._has_close_breakdown(stats):
            sections.append(self._section("CURRENT COLLECTION CLOSE BREAKDOWN", [
                ("Automatic", int(stats.get("automatic_closed", 0))),
                ("Target", int(stats.get("target_closed", 0))),
                ("Timeout", int(stats.get("timeout_closed", 0))),
                ("Timeout Profit", int(stats.get("timeout_profit", 0))),
                ("Timeout Breakeven", int(stats.get("timeout_breakeven", 0))),
                ("Timeout Loss", int(stats.get("timeout_loss", 0))),
                ("Manual", int(stats.get("manual_closed", 0))),
            ]))
        if self._has_direction_breakdown(stats):
            sections.append(self._section("CURRENT COLLECTION DIRECTION BREAKDOWN", [
                ("BUY Count", int(stats.get("buy_count", 0))),
                ("BUY Net", self._format_signed(float(stats.get("buy_total_pnl", 0.0)))),
                ("BUY Win Rate", self._format_percent(float(stats.get("buy_win_rate", 0.0)))),
                ("SELL Count", int(stats.get("sell_count", 0))),
                ("SELL Net", self._format_signed(float(stats.get("sell_total_pnl", 0.0)))),
                ("SELL Win Rate", self._format_percent(float(stats.get("sell_win_rate", 0.0)))),
            ]))
        if nearest_open_cycle is not None:
            sections.append(self._current_cycle_section(nearest_open_cycle))
        sections.append(self._market_signal_section(
            current_price=current_price,
            data_source=data_source,
            price_timestamp=price_timestamp,
            entry_diagnostics=entry_diagnostics,
        ))
        safety = self._safety_section(entry_diagnostics)
        if safety is not None:
            sections.append(safety)
        self._render_sections(sections)

    def render_collection_progress_compact(
        self,
        stats: dict[str, float | int],
        target: int,
        *,
        iteration: int,
        price_info: tuple[float, str, str] | None,
        nearest_open_cycle,
        action_taken: str,
        entry_diagnostics: dict[str, str],
        last_closed_cycle: dict | None = None,
        lifetime_stats: dict[str, float | int] | None = None,
        collection_id: str | int | None = None,
        tracking_limit_seconds: float | None = None,
    ) -> None:
        current_price, _data_source, _price_timestamp = price_info if price_info else (None, "N/A", "N/A")
        lifetime = lifetime_stats or {}
        collection_label = collection_id if collection_id is not None else iteration
        title = (
            f"collection {collection_label} | "
            f"new {int(stats['closed_cycles'])}/{target}"
        )
        if iteration is not None:
            title = f"{title} | update {iteration}"
        self._render_rule(title)
        print(
            "New: "
            f"{int(stats['closed_cycles'])}/{target} | "
            f"Lifetime: {int(lifetime.get('closed_cycles', 0))} | "
            f"Open: {int(stats.get('open_cycles', 0))} | "
            f"New Profit: {self._format_signed(float(stats.get('net_profit', 0.0)))} | "
            f"New Profit NoExt: {self._format_signed(float(stats.get('net_profit_without_extreme', stats.get('net_profit', 0.0))))} | "
            f"New Extreme Profit: {self._format_signed(float(stats.get('extreme_profit', 0.0)))} | "
            f"Extreme: {int(stats.get('extreme_cycles', 0))} | "
            f"NonExt: {int(stats.get('non_extreme_cycles', stats.get('closed_cycles', 0)))} | "
            f"New Win: {self._format_percent(float(stats.get('win_rate', 0.0)))} | "
            f"New Win NoExt: {self._format_percent(float(stats.get('win_rate_without_extreme', stats.get('win_rate', 0.0))))} | "
            f"Lifetime Profit: {self._format_signed(float(lifetime.get('net_profit', 0.0)))} | "
            f"Action: {action_taken}"
        )
        if action_taken == "closed" and last_closed_cycle is not None:
            self._print_compact_closed_cycle(last_closed_cycle)
            return
        if nearest_open_cycle is not None:
            print(
                "Cycle: "
                f"{getattr(nearest_open_cycle, 'direction', 'N/A')} | "
                f"Price: {self._format_float(getattr(nearest_open_cycle, 'current_price', current_price))} | "
                f"Target: {self._format_float(getattr(nearest_open_cycle, 'target_price', None))} | "
                f"Remain: {self._format_float(getattr(nearest_open_cycle, 'distance_to_target', None))} | "
                "Tracking: "
                f"{self._format_seconds(getattr(nearest_open_cycle, 'age_seconds', None))}"
                f"{self._format_tracking_limit(tracking_limit_seconds)} | "
                f"uPnL: {self._format_signed(getattr(nearest_open_cycle, 'unrealized_pnl', 0.0))}"
            )
            if action_taken == "opened" and self._is_useful(entry_diagnostics.get("extreme_signal_detected")):
                self._print_compact_extreme_signal(entry_diagnostics)
            return
        print(
            "Price: "
            f"{self._format_compact_float(current_price)} | "
            f"Center: {self._compact_text(entry_diagnostics.get('short_center'))} | "
            f"Mode: {self._compact_text(entry_diagnostics.get('hf_entry_mode'))} | "
            f"Candidate: {self._compact_text(entry_diagnostics.get('candidate_detected'))} | "
            f"Block: {self._compact_text(entry_diagnostics.get('entry_block_reason'))}"
        )
        if self._is_useful(entry_diagnostics.get("extreme_signal_detected")):
            self._print_compact_extreme_signal(entry_diagnostics)

    def _print_compact_extreme_signal(self, entry_diagnostics: dict[str, str]) -> None:
        print(
            "Extreme: "
            f"signal={self._compact_text(entry_diagnostics.get('extreme_signal_detected'))} | "
            f"session={self._compact_text(entry_diagnostics.get('session_signal'))} | "
            f"velocity={self._compact_text(entry_diagnostics.get('velocity_spike_signal'))} | "
            f"velocity_value={self._compact_text(entry_diagnostics.get('price_velocity'))}/"
            f"{self._compact_text(entry_diagnostics.get('velocity_threshold'))} | "
            f"compression={self._compact_text(entry_diagnostics.get('compression_signal'))} | "
            f"compression_score={self._compact_text(entry_diagnostics.get('compression_score'))}/"
            f"{self._compact_text(entry_diagnostics.get('compression_threshold'))} | "
            f"extreme_price_guard={self._compact_text(entry_diagnostics.get('extreme_price_guard'))} | "
            f"excessive_velocity_guard={self._compact_text(entry_diagnostics.get('excessive_velocity_guard'))} | "
            f"distance_from_center={self._compact_text(entry_diagnostics.get('distance_from_center'))}/"
            f"{self._compact_text(entry_diagnostics.get('max_allowed_distance'))} | "
            f"post_extreme_rebound_risk={self._compact_text(entry_diagnostics.get('post_extreme_rebound_risk'))} | "
            f"strength={self._compact_text(entry_diagnostics.get('signal_strength'))} | "
            f"expected={self._compact_text(entry_diagnostics.get('expected_direction'))} | "
            f"lead_warning={self._compact_text(entry_diagnostics.get('lead_time_warning'))}"
        )

    def _print_compact_closed_cycle(self, cycle: dict) -> None:
        print(
            "Closed Cycle: "
            f"db_id={self._compact_text(cycle.get('db_id'))} | "
            f"profile={self._compact_text(cycle.get('profile'))} | "
            f"direction={self._compact_text(cycle.get('direction'))} | "
            f"reason={self._compact_text(cycle.get('close_reason'))} | "
            f"net={self._format_signed(float(cycle.get('net_profit', 0.0)))}"
        )
        print(
            "Closed Prices: "
            f"open={self._format_float(cycle.get('open_price'))} | "
            f"close={self._format_float(cycle.get('close_price'))} | "
            f"target={self._format_float(cycle.get('target_price'))} | "
            f"distance={self._format_float(cycle.get('distance_to_target_at_close'))} | "
            f"holding={self._format_seconds(cycle.get('holding_seconds'))}"
        )
        print(
            "Closed Flags: "
            f"target_hit={self._compact_text(cycle.get('target_hit'))} | "
            f"timeout_hit={self._compact_text(cycle.get('timeout_hit'))} | "
            f"was_extreme_close={self._compact_text(cycle.get('was_extreme_close'))} | "
            f"breakeven_close={self._compact_text(cycle.get('breakeven_close'))} | "
            f"possible_reason={self._compact_text(cycle.get('possible_reason'))}"
        )
        if cycle.get("profile") != "extreme_strategy_v1":
            return
        print(
            "Extreme Entry: "
            f"signal={self._compact_text(cycle.get('extreme_signal_at_entry'))} | "
            f"strength={self._format_float(cycle.get('entry_signal_strength'))} | "
            f"velocity={self._format_float(cycle.get('entry_velocity_value'))}/"
            f"{self._format_float(cycle.get('entry_velocity_threshold'))} | "
            f"compression={self._format_float(cycle.get('entry_compression_score'))}/"
            f"{self._format_float(cycle.get('entry_compression_threshold'))} | "
            f"expected={self._compact_text(cycle.get('expected_direction'))} | "
            f"lead_warning={self._compact_text(cycle.get('lead_warning'))} | "
            f"false_positive_hint={self._compact_text(cycle.get('false_positive_hint'))}"
        )

    def render_collection_summary(
        self,
        stats: dict[str, float | int],
        *,
        lifetime_stats: dict[str, float | int] | None = None,
        collection_id: str | int | None = None,
        profile: str | None = None,
    ) -> None:
        lifetime = lifetime_stats or {}
        sections = [
            self._section("NEW COLLECTION SUMMARY", [
                ("Collection ID", collection_id or "N/A"),
                ("Profile", profile or "N/A"),
                ("New closed cycles", int(stats["closed_cycles"])),
                ("New automatic closed", int(stats["automatic_closed"])),
                ("New target closed", int(stats["target_closed"])),
                ("New timeout closed", int(stats["timeout_closed"])),
                ("New breakeven closed", int(stats.get("breakeven_cycles", 0))),
                ("New zero-net cycles", int(stats.get("zero_net_cycles", stats.get("breakeven_cycles", 0)))),
                ("New extreme_target closed", int(stats.get("extreme_target_closed", 0))),
                ("New extreme_timeout closed", int(stats.get("extreme_timeout_closed", 0))),
                ("New timeout profit", int(stats.get("timeout_profit", 0))),
                ("New timeout breakeven", int(stats.get("timeout_breakeven", 0))),
                ("New timeout loss", int(stats.get("timeout_loss", 0))),
                ("New manual closed", int(stats["manual_closed"])),
                ("New net profit", self._format_signed(float(stats["net_profit"]))),
                ("New net profit without extreme", self._format_signed(float(stats.get("net_profit_without_extreme", stats["net_profit"])))),
                ("New extreme profit", self._format_signed(float(stats.get("extreme_profit", 0.0)))),
                ("New extreme cycles", int(stats.get("extreme_cycles", 0))),
                ("New non-extreme cycles", int(stats.get("non_extreme_cycles", stats["closed_cycles"]))),
                ("Extreme profit share", self._format_percent(float(stats.get("extreme_profit_share", 0.0)))),
                ("New win rate", self._format_percent(float(stats["win_rate"]))),
                ("New win rate without extreme", self._format_percent(float(stats.get("win_rate_without_extreme", stats["win_rate"])))),
                ("New average cycle PnL", self._format_signed(float(stats.get("average_cycle_pnl", 0.0)))),
                ("New expectancy", self._format_signed(float(stats.get("expectancy", 0.0)))),
                ("New profit factor", f"{float(stats.get('profit_factor', 0.0)):.4f}"),
            ]),
            self._section("LIFETIME SUMMARY", [
                ("Lifetime closed cycles", int(lifetime.get("closed_cycles", 0))),
                ("Lifetime net profit", self._format_signed(float(lifetime.get("net_profit", 0.0)))),
                ("Lifetime win rate", self._format_percent(float(lifetime.get("win_rate", 0.0)))),
            ]),
            self._section("EXECUTION QUALITY", [
                ("Missed target cycles", int(stats.get("missed_target_count", 0))),
                ("Missed target then loss", int(stats.get("missed_target_then_loss_count", 0))),
                ("Average MFE", self._format_float(float(stats.get("average_mfe", 0.0)))),
                ("Average MAE", self._format_float(float(stats.get("average_mae", 0.0)))),
                ("Average missed PnL", self._format_float(float(stats.get("average_missed_pnl", 0.0)))),
                ("Worst adverse move", self._format_float(float(stats.get("worst_adverse_move", 0.0)))),
            ]),
        ]
        warning = stats.get("extreme_warning")
        if self._is_useful(warning):
            sections.append(self._section("EXTREME RUN WARNING", [
                ("Warning", warning),
                ("Recommendation", stats.get("extreme_recommendation")),
            ]))
        self._render_sections(sections)

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

    def render_recovery_required(self, message: str | None = None, cycle: dict[str, Any] | None = None) -> None:
        text = message or (
            "Open cycle detected from previous session. "
            "Automatic close is disabled. Choose recovery action before continuing."
        )
        rows = [("Warning", text)]
        if cycle:
            db_id = cycle.get("db_id")
            rows.extend([
                ("DB ID", db_id),
                ("Direction", cycle.get("direction")),
                ("Entry Price", self._format_float(cycle.get("open_price"))),
                ("Target Price", self._format_float(cycle.get("target_price"))),
                ("Current Price", self._format_recovery_float(cycle.get("current_price"))),
                ("Distance Target", self._format_recovery_distance(cycle)),
                ("Target Status", cycle.get("target_status", "unknown")),
                ("Est. PnL Now", self._format_recovery_signed(cycle.get("estimated_pnl_now"))),
                ("Decision Hint", cycle.get("decision_hint", "operator decision required")),
                ("Opened Session", cycle.get("opened_session_id")),
                ("Current Session", cycle.get("current_session_id")),
                ("Opened At", cycle.get("opened_at")),
                ("Elapsed since opened", cycle.get("elapsed")),
                ("Active tracking", cycle.get("active_tracking", "paused")),
                ("Recovery Status", cycle.get("recovery_status")),
            ])
        rows.extend([
            ("Automatic close", "DISABLED"),
            (
                "Resume",
                f"python manage.py paper-recovery-action --db-id {cycle.get('db_id')} --action resume"
                if cycle
                else None,
            ),
            (
                "Manual close",
                f"python manage.py paper-close-cycle --db-id {cycle.get('db_id')} --reason manual"
                if cycle
                else None,
            ),
            (
                "Abandon",
                f"python manage.py paper-recovery-action --db-id {cycle.get('db_id')} --action abandon --reason stale"
                if cycle
                else None,
            ),
            ("Required action", "resume / close manually / abandon"),
        ])
        self._render_sections([self._section("RECOVERY REQUIRED", rows)])

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
            ("Extreme Signal", entry_diagnostics.get("extreme_signal_detected")),
            ("Session Signal", entry_diagnostics.get("session_signal")),
            ("Velocity Spike", entry_diagnostics.get("velocity_spike_signal")),
            ("Compression Signal", entry_diagnostics.get("compression_signal")),
            ("Signal Strength", entry_diagnostics.get("signal_strength")),
            ("Expected Direction", entry_diagnostics.get("expected_direction")),
            ("Lead Time Warning", entry_diagnostics.get("lead_time_warning")),
            ("Max Holding", entry_diagnostics.get("max_holding")),
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

    @staticmethod
    def _has_close_breakdown(stats: dict[str, float | int]) -> bool:
        return any(int(stats.get(key, 0)) for key in ("target_closed", "timeout_closed", "manual_closed"))

    @staticmethod
    def _has_direction_breakdown(stats: dict[str, float | int]) -> bool:
        return int(stats.get("buy_count", 0)) > 0 or int(stats.get("sell_count", 0)) > 0

    def _render_rule(self, title: str) -> None:
        if self._rich_enabled:
            self._console.rule(title)
            return
        print("-" * 80)
        print(f"-- {title} --")

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
    def _format_recovery_float(value: Any) -> str:
        if value is None or str(value) in {"", "N/A", "None", "unavailable"}:
            return "unavailable"
        return f"{float(value):.8f}"

    @staticmethod
    def _format_recovery_signed(value: Any) -> str:
        if value is None or str(value) in {"", "N/A", "None", "unavailable"}:
            return "unavailable"
        return f"{float(value):+.8f}"

    def _format_recovery_distance(self, cycle: dict[str, Any]) -> str:
        if cycle.get("target_status") == "reached":
            return "reached"
        return self._format_recovery_float(cycle.get("distance_to_target"))

    @staticmethod
    def _format_compact_float(value: Any) -> str:
        if value is None or str(value) == "N/A":
            return "unavailable"
        return f"{float(value):.8f}"

    @staticmethod
    def _compact_text(value: Any) -> str:
        if value is None or str(value) in {"", "N/A", "None"}:
            return "unavailable"
        return str(value)

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
        seconds = int(float(value))
        if seconds < 60:
            return f"{seconds}s"
        minutes, remaining_seconds = divmod(seconds, 60)
        return f"{minutes}m {remaining_seconds}s"

    def _format_tracking_limit(self, value: Any) -> str:
        if value is None or str(value) in {"", "N/A", "None"}:
            return ""
        return f" / {self._format_seconds(value)}"
