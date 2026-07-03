from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean

from app.text_encoding import clean_display_text
from storage.database_manager import DatabaseManager


EXTREME_PROFILE = "extreme_strategy_v1"
DEFAULT_COMPRESSION_THRESHOLD = 60.0


@dataclass(frozen=True)
class ExtremePaperSignalCycle:
    db_id: int
    direction: str
    open_price: float
    close_price: float
    net_profit: float
    close_reason: str
    opened_at: str
    closed_at: str | None
    holding_seconds: float | None
    session_signal: str
    velocity_spike_signal: str
    compression_signal: str
    signal_strength: float | None
    lead_warning: str
    expected_direction: str
    entry_direction: str
    velocity_value: float | None
    velocity_threshold: float | None
    compression_score: float | None
    compression_threshold: float | None
    movement_5s: float | None
    movement_15s: float | None
    movement_30s: float | None
    movement_60s: float | None
    max_favorable_excursion: float
    max_adverse_excursion: float
    extreme_target_approached: bool
    false_positive_category: str


@dataclass(frozen=True)
class ExtremePaperSignalSummary:
    profile: str
    total_cycles: int
    target_closed: int
    timeout_closed: int
    false_positives: int
    average_signal_strength_winners: float | None
    average_signal_strength_losers: float | None
    average_velocity_winners: float | None
    average_velocity_losers: float | None
    average_compression_winners: float | None
    average_compression_losers: float | None
    lead_warning_count: int
    recommendation: str
    cycles: list[ExtremePaperSignalCycle]


class ExtremePaperSignalDiagnosticsEngine:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def build_report(
        self,
        profile: str = EXTREME_PROFILE,
        limit: int | None = None,
    ) -> ExtremePaperSignalSummary:
        rows = self._load_rows(profile, limit)
        cycles = [self._build_cycle(row) for row in rows]
        winners = [cycle for cycle in cycles if cycle.net_profit > 0]
        losers = [cycle for cycle in cycles if cycle.net_profit < 0]

        return ExtremePaperSignalSummary(
            profile=profile,
            total_cycles=len(cycles),
            target_closed=sum(1 for cycle in cycles if self._is_target_reason(cycle.close_reason)),
            timeout_closed=sum(1 for cycle in cycles if self._is_timeout_reason(cycle.close_reason)),
            false_positives=sum(1 for cycle in cycles if cycle.net_profit < 0),
            average_signal_strength_winners=self._average_optional([cycle.signal_strength for cycle in winners]),
            average_signal_strength_losers=self._average_optional([cycle.signal_strength for cycle in losers]),
            average_velocity_winners=self._average_optional([cycle.velocity_value for cycle in winners]),
            average_velocity_losers=self._average_optional([cycle.velocity_value for cycle in losers]),
            average_compression_winners=self._average_optional([cycle.compression_score for cycle in winners]),
            average_compression_losers=self._average_optional([cycle.compression_score for cycle in losers]),
            lead_warning_count=sum(1 for cycle in cycles if cycle.lead_warning.lower() == "yes"),
            recommendation=self._recommendation(cycles),
            cycles=cycles,
        )

    def _load_rows(self, profile: str, limit: int | None) -> list[dict]:
        sql = """
            SELECT
                c.id, c.direction, c.open_price, c.close_price, c.net_profit,
                c.close_reason, c.opened_at, c.closed_at, c.max_favorable_pnl,
                c.max_adverse_pnl, c.min_distance_to_target, c.was_near_target,
                d.session_signal, d.velocity_spike_signal, d.compression_signal,
                d.signal_strength, d.lead_warning, d.expected_direction,
                d.entry_direction, d.velocity_value, d.velocity_threshold,
                d.compression_score, d.compression_threshold
            FROM paper_cycles c
            LEFT JOIN hf_paper_cycle_entry_diagnostics d ON d.paper_cycle_id = c.id
            WHERE c.strategy_profile = ?
            ORDER BY c.opened_at ASC
        """
        params: tuple = (profile,)
        if limit is not None:
            sql += " LIMIT ?"
            params = (profile, int(limit))

        with self.database.connect() as conn:
            rows = conn.execute(sql, params).fetchall()

        keys = [
            "db_id",
            "direction",
            "open_price",
            "close_price",
            "net_profit",
            "close_reason",
            "opened_at",
            "closed_at",
            "max_favorable_pnl",
            "max_adverse_pnl",
            "min_distance_to_target",
            "was_near_target",
            "session_signal",
            "velocity_spike_signal",
            "compression_signal",
            "signal_strength",
            "lead_warning",
            "expected_direction",
            "entry_direction",
            "velocity_value",
            "velocity_threshold",
            "compression_score",
            "compression_threshold",
        ]
        return [dict(zip(keys, row, strict=False)) for row in rows]

    def _build_cycle(self, row: dict) -> ExtremePaperSignalCycle:
        opened_at = clean_display_text(row["opened_at"])
        closed_at = clean_display_text(row["closed_at"]) if row.get("closed_at") else None
        holding_seconds = self._holding_seconds(opened_at, closed_at)
        direction = clean_display_text(row["direction"])
        open_price = float(row["open_price"] or 0.0)
        close_price = float(row["close_price"] or 0.0)
        movement_by_seconds = self._price_movements_after_entry(opened_at, direction, open_price)
        signal_strength = self._optional_float(row.get("signal_strength"))
        velocity_value = self._optional_float(row.get("velocity_value"))
        velocity_threshold = self._optional_float(row.get("velocity_threshold"))
        compression_score = self._optional_float(row.get("compression_score"))
        compression_threshold = self._optional_float(row.get("compression_threshold")) or DEFAULT_COMPRESSION_THRESHOLD
        max_favorable = float(row.get("max_favorable_pnl") or 0.0)
        max_adverse = float(row.get("max_adverse_pnl") or 0.0)
        target_approached = bool(row.get("was_near_target")) or self._target_approached(
            self._optional_float(row.get("min_distance_to_target"))
        )
        category = self._false_positive_category(
            net_profit=float(row["net_profit"] or 0.0),
            direction=direction,
            open_price=open_price,
            close_price=close_price,
            max_favorable=max_favorable,
            velocity_value=velocity_value,
            velocity_threshold=velocity_threshold,
            compression_score=compression_score,
            compression_threshold=compression_threshold,
            lead_warning=clean_display_text(row.get("lead_warning") or "N/A"),
        )

        return ExtremePaperSignalCycle(
            db_id=int(row["db_id"]),
            direction=direction,
            open_price=open_price,
            close_price=close_price,
            net_profit=float(row["net_profit"] or 0.0),
            close_reason=clean_display_text(row.get("close_reason") or "N/A"),
            opened_at=opened_at,
            closed_at=closed_at,
            holding_seconds=holding_seconds,
            session_signal=self._bool_label(row.get("session_signal")),
            velocity_spike_signal=self._bool_label(row.get("velocity_spike_signal")),
            compression_signal=self._bool_label(row.get("compression_signal")),
            signal_strength=signal_strength,
            lead_warning=clean_display_text(row.get("lead_warning") or "N/A"),
            expected_direction=clean_display_text(row.get("expected_direction") or "N/A"),
            entry_direction=clean_display_text(row.get("entry_direction") or "N/A"),
            velocity_value=velocity_value,
            velocity_threshold=velocity_threshold,
            compression_score=compression_score,
            compression_threshold=compression_threshold,
            movement_5s=movement_by_seconds[5],
            movement_15s=movement_by_seconds[15],
            movement_30s=movement_by_seconds[30],
            movement_60s=movement_by_seconds[60],
            max_favorable_excursion=max_favorable,
            max_adverse_excursion=max_adverse,
            extreme_target_approached=target_approached,
            false_positive_category=category,
        )

    def _price_movements_after_entry(self, opened_at: str, direction: str, open_price: float) -> dict[int, float | None]:
        result: dict[int, float | None] = {5: None, 15: None, 30: None, 60: None}
        try:
            opened = datetime.fromisoformat(opened_at)
        except ValueError:
            return result

        with self.database.connect() as conn:
            for seconds in result:
                target_time = (opened + timedelta(seconds=seconds)).isoformat()
                row = conn.execute(
                    """
                    SELECT price
                    FROM market_snapshots_hf
                    WHERE timestamp >= ?
                    ORDER BY timestamp ASC
                    LIMIT 1
                    """,
                    (target_time,),
                ).fetchone()
                if not row:
                    continue
                price = float(row[0])
                result[seconds] = price - open_price if direction == "BUY_USDC" else open_price - price
        return result

    @staticmethod
    def _false_positive_category(
        *,
        net_profit: float,
        direction: str,
        open_price: float,
        close_price: float,
        max_favorable: float,
        velocity_value: float | None,
        velocity_threshold: float | None,
        compression_score: float | None,
        compression_threshold: float | None,
        lead_warning: str,
    ) -> str:
        if net_profit >= 0:
            return "N/A"
        if velocity_value is None or velocity_threshold is None or compression_score is None:
            return "unknown"
        if abs(velocity_value) <= abs(velocity_threshold) * 1.5:
            return "weak_velocity_spike"
        if lead_warning.lower() == "yes":
            return "late_entry"
        if compression_score >= (compression_threshold or DEFAULT_COMPRESSION_THRESHOLD) and max_favorable <= 0:
            return "compression_without_breakout"
        moved_against = (
            close_price < open_price
            if direction == "BUY_USDC"
            else close_price > open_price
        )
        if moved_against:
            return "wrong_direction"
        if max_favorable <= 0:
            return "insufficient_follow_through"
        return "signal_noise"

    @staticmethod
    def _recommendation(cycles: list[ExtremePaperSignalCycle]) -> str:
        if not cycles:
            return "NEED_MORE_DATA"
        if len(cycles) < 20:
            return "KEEP_COLLECTING"
        false_rate = sum(1 for cycle in cycles if cycle.net_profit < 0) / len(cycles)
        if false_rate >= 0.5:
            return "TUNE_SIGNAL_THRESHOLDS"
        if false_rate <= 0.25 and len(cycles) >= 50:
            return "READY_FOR_LONGER_PAPER"
        return "KEEP_COLLECTING"

    @staticmethod
    def _holding_seconds(opened_at: str, closed_at: str | None) -> float | None:
        if not closed_at:
            return None
        try:
            return max(0.0, (datetime.fromisoformat(closed_at) - datetime.fromisoformat(opened_at)).total_seconds())
        except ValueError:
            return None

    @staticmethod
    def _target_approached(min_distance: float | None) -> bool:
        return min_distance is not None and min_distance <= 0.000005

    @staticmethod
    def _bool_label(value) -> str:
        if value is None:
            return "N/A"
        return "yes" if bool(value) else "no"

    @staticmethod
    def _optional_float(value) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _average_optional(values: list[float | None]) -> float | None:
        clean = [float(value) for value in values if value is not None]
        return mean(clean) if clean else None

    @staticmethod
    def _is_target_reason(reason: str) -> bool:
        value = clean_display_text(reason).lower()
        return value == "target" or "target" in value

    @staticmethod
    def _is_timeout_reason(reason: str) -> bool:
        value = clean_display_text(reason).lower()
        return value.startswith("max_holding_") or "timeout" in value
