from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager
from trading.fee_engine import FeeEngine


MAX_HOLDING_THRESHOLDS_SECONDS = (
    30 * 60,
    60 * 60,
    2 * 60 * 60,
    4 * 60 * 60,
    8 * 60 * 60,
    12 * 60 * 60,
    24 * 60 * 60,
)


@dataclass(frozen=True)
class MaxHoldingSensitivityResult:
    max_age_seconds: int
    cycles_affected: int
    would_close_by_timeout: int
    timeout_close_estimated_pnl: float
    realized_target_closes: int
    combined_pnl: float
    win_rate_including_timeouts: float
    worst_timeout_loss: float | None
    recommendation_score: float


@dataclass(frozen=True)
class MaxHoldingSensitivityReport:
    profile: str
    current_price: float
    current_price_source: str
    current_price_timestamp: str
    total_cycles: int
    results: list[MaxHoldingSensitivityResult]
    recommended_max_age_seconds: int | None


class MaxHoldingSensitivityEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.database = database
        self.config = config
        self.fee_engine = FeeEngine(config)

    def build_report(
        self,
        *,
        profile: str,
        current_price: float,
        current_price_source: str = "UNKNOWN",
        current_price_timestamp: str = "UNKNOWN",
        thresholds: tuple[int, ...] = MAX_HOLDING_THRESHOLDS_SECONDS,
    ) -> MaxHoldingSensitivityReport:
        cycles = self._load_profile_cycles(profile)
        snapshots = self._load_snapshots()
        results = [
            self._evaluate_threshold(cycles, snapshots, current_price, threshold)
            for threshold in thresholds
        ]
        recommended = max(results, key=lambda item: item.recommendation_score).max_age_seconds if results else None
        return MaxHoldingSensitivityReport(
            profile=profile,
            current_price=current_price,
            current_price_source=current_price_source,
            current_price_timestamp=current_price_timestamp,
            total_cycles=len(cycles),
            results=results,
            recommended_max_age_seconds=recommended,
        )

    def _evaluate_threshold(
        self,
        cycles: list[dict],
        snapshots: list[dict],
        current_price: float,
        threshold_seconds: int,
    ) -> MaxHoldingSensitivityResult:
        target_pnls: list[float] = []
        timeout_pnls: list[float] = []
        wins = 0

        for cycle in cycles:
            duration = self._duration_or_age_seconds(cycle)
            if cycle["status"] == "CLOSED" and duration is not None and duration <= threshold_seconds:
                target_pnls.append(cycle["net_profit"])
                if cycle["net_profit"] > 0:
                    wins += 1
                continue

            if duration is not None and duration >= threshold_seconds:
                timeout_price = self._timeout_price(
                    cycle=cycle,
                    snapshots=snapshots,
                    threshold_seconds=threshold_seconds,
                    current_price=current_price,
                )
                timeout_pnl = self.fee_engine.calculate_profit(
                    direction=cycle["direction"],
                    open_price=cycle["open_price"],
                    close_price=timeout_price,
                    quantity=cycle["quantity"],
                    use_taker_fee=True,
                ).net_profit
                timeout_pnls.append(timeout_pnl)
                if timeout_pnl > 0:
                    wins += 1

        affected = len(target_pnls) + len(timeout_pnls)
        combined_pnl = sum(target_pnls) + sum(timeout_pnls)
        worst_timeout_loss = min(timeout_pnls) if timeout_pnls else None
        win_rate = wins / affected if affected else 0.0
        score = self._score(
            combined_pnl=combined_pnl,
            win_rate=win_rate,
            worst_timeout_loss=worst_timeout_loss,
            timeout_count=len(timeout_pnls),
            affected=affected,
        )
        return MaxHoldingSensitivityResult(
            max_age_seconds=threshold_seconds,
            cycles_affected=affected,
            would_close_by_timeout=len(timeout_pnls),
            timeout_close_estimated_pnl=sum(timeout_pnls),
            realized_target_closes=len(target_pnls),
            combined_pnl=combined_pnl,
            win_rate_including_timeouts=win_rate,
            worst_timeout_loss=worst_timeout_loss,
            recommendation_score=score,
        )

    def _load_profile_cycles(self, profile: str) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, cycle_id, strategy_profile, direction, status,
                       open_price, close_price, quantity, gross_profit,
                       net_profit, opened_at, closed_at
                FROM paper_cycles
                WHERE strategy_profile = ?
                ORDER BY opened_at ASC
                """,
                (profile,),
            ).fetchall()

        return [
            {
                "db_id": int(db_id),
                "cycle_id": int(cycle_id),
                "profile": clean_display_text(strategy_profile or "UNKNOWN"),
                "direction": clean_display_text(direction),
                "status": clean_display_text(status),
                "open_price": float(open_price),
                "close_price": float(close_price),
                "quantity": float(quantity),
                "gross_profit": float(gross_profit),
                "net_profit": float(net_profit),
                "opened_at": clean_display_text(opened_at),
                "closed_at": clean_display_text(closed_at) if closed_at else None,
            }
            for (
                db_id,
                cycle_id,
                strategy_profile,
                direction,
                status,
                open_price,
                close_price,
                quantity,
                gross_profit,
                net_profit,
                opened_at,
                closed_at,
            ) in rows
        ]

    def _load_snapshots(self) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT timestamp, price
                FROM market_snapshots
                ORDER BY timestamp ASC
                """
            ).fetchall()
        return [
            {"timestamp": clean_display_text(timestamp), "price": float(price)}
            for timestamp, price in rows
        ]

    def _timeout_price(
        self,
        *,
        cycle: dict,
        snapshots: list[dict],
        threshold_seconds: int,
        current_price: float,
    ) -> float:
        target_time = datetime.fromisoformat(cycle["opened_at"]) + timedelta(seconds=threshold_seconds)
        for snapshot in snapshots:
            try:
                snapshot_time = datetime.fromisoformat(snapshot["timestamp"])
            except ValueError:
                continue
            if snapshot_time >= target_time:
                return snapshot["price"]

        if cycle["status"] == "CLOSED":
            return float(cycle["close_price"])
        return current_price

    def _duration_or_age_seconds(self, cycle: dict) -> float | None:
        if cycle["closed_at"]:
            opened_at = datetime.fromisoformat(cycle["opened_at"])
            closed_at = datetime.fromisoformat(cycle["closed_at"])
            return max(0.0, (closed_at - opened_at).total_seconds())
        opened_at = datetime.fromisoformat(cycle["opened_at"])
        now = datetime.now(tz=opened_at.tzinfo) if opened_at.tzinfo else datetime.now()
        return max(0.0, (now - opened_at).total_seconds())

    @staticmethod
    def _score(
        *,
        combined_pnl: float,
        win_rate: float,
        worst_timeout_loss: float | None,
        timeout_count: int,
        affected: int,
    ) -> float:
        loss_penalty = abs(worst_timeout_loss) if worst_timeout_loss is not None and worst_timeout_loss < 0 else 0.0
        timeout_penalty = (timeout_count / affected) * 0.001 if affected else 0.0
        return combined_pnl + win_rate * 0.01 - loss_penalty - timeout_penalty
