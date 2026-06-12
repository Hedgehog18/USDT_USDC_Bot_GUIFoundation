from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager
from trading.fee_engine import FeeEngine


STOP_LOSS_THRESHOLDS_PERCENT = (0.005, 0.01, 0.02, 0.03, 0.05)
MAX_HOLDING_THRESHOLDS_SECONDS = (
    30 * 60,
    60 * 60,
    2 * 60 * 60,
    4 * 60 * 60,
    8 * 60 * 60,
)


@dataclass(frozen=True)
class OpenCycleExitRisk:
    db_id: int
    direction: str
    profile: str
    age_seconds: float
    open_price: float
    current_price: float
    target_price: float
    unrealized_pnl: float
    distance_to_target: float
    adverse_move_percent: float
    would_stop_at: dict[float, bool]


@dataclass(frozen=True)
class ExitRiskHistoricalSummary:
    closed_net_profit: float
    open_unrealized_pnl: float
    combined_realized_unrealized_pnl: float
    best_closed_profit: float | None
    worst_open_unrealized_loss: float | None
    avg_holding_time_closed_seconds: float | None
    avg_age_open_seconds: float | None


@dataclass(frozen=True)
class MaxHoldingSimulationResult:
    max_age_seconds: int
    would_timeout_count: int


@dataclass(frozen=True)
class ExitRiskDiagnosticsReport:
    profile: str
    current_price: float
    current_price_source: str
    current_price_timestamp: str
    open_cycles: list[OpenCycleExitRisk]
    historical_summary: ExitRiskHistoricalSummary
    max_holding_results: list[MaxHoldingSimulationResult]
    recommendation: str


class ExitRiskDiagnosticsEngine:
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
    ) -> ExitRiskDiagnosticsReport:
        rows = self._load_profile_cycles(profile)
        open_rows = [row for row in rows if row["status"] == "OPEN"]
        closed_rows = [row for row in rows if row["status"] == "CLOSED"]
        open_cycles = [self._build_open_cycle(row, current_price) for row in open_rows]
        historical_summary = self._build_historical_summary(
            open_cycles=open_cycles,
            closed_rows=closed_rows,
        )
        max_holding_results = [
            MaxHoldingSimulationResult(
                max_age_seconds=threshold,
                would_timeout_count=self._would_timeout_count(rows, threshold),
            )
            for threshold in MAX_HOLDING_THRESHOLDS_SECONDS
        ]
        return ExitRiskDiagnosticsReport(
            profile=profile,
            current_price=current_price,
            current_price_source=current_price_source,
            current_price_timestamp=current_price_timestamp,
            open_cycles=open_cycles,
            historical_summary=historical_summary,
            max_holding_results=max_holding_results,
            recommendation=self._recommend(open_cycles, max_holding_results),
        )

    def _load_profile_cycles(self, profile: str) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, cycle_id, strategy_profile, direction, status,
                       open_price, close_price, quantity, open_fee, close_fee,
                       gross_profit, net_profit, opened_at, closed_at
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
                "open_fee": float(open_fee),
                "close_fee": float(close_fee),
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
                open_fee,
                close_fee,
                gross_profit,
                net_profit,
                opened_at,
                closed_at,
            ) in rows
        ]

    def _build_open_cycle(self, row: dict, current_price: float) -> OpenCycleExitRisk:
        unrealized = self.fee_engine.calculate_profit(
            direction=row["direction"],
            open_price=row["open_price"],
            close_price=current_price,
            quantity=row["quantity"],
            use_taker_fee=True,
        ).net_profit
        adverse_move_percent = self._adverse_move_percent(
            direction=row["direction"],
            open_price=row["open_price"],
            current_price=current_price,
        )
        return OpenCycleExitRisk(
            db_id=row["db_id"],
            direction=row["direction"],
            profile=row["profile"],
            age_seconds=self._age_seconds(row),
            open_price=row["open_price"],
            current_price=current_price,
            target_price=row["close_price"],
            unrealized_pnl=unrealized,
            distance_to_target=self._distance_to_target(row["direction"], current_price, row["close_price"]),
            adverse_move_percent=adverse_move_percent,
            would_stop_at={
                threshold: adverse_move_percent >= threshold
                for threshold in STOP_LOSS_THRESHOLDS_PERCENT
            },
        )

    def _build_historical_summary(
        self,
        *,
        open_cycles: list[OpenCycleExitRisk],
        closed_rows: list[dict],
    ) -> ExitRiskHistoricalSummary:
        closed_net_profit = sum(row["net_profit"] for row in closed_rows)
        open_unrealized_pnl = sum(item.unrealized_pnl for item in open_cycles)
        closed_durations = [
            self._duration_seconds(row)
            for row in closed_rows
            if self._duration_seconds(row) is not None
        ]
        open_ages = [item.age_seconds for item in open_cycles]
        open_losses = [item.unrealized_pnl for item in open_cycles]
        return ExitRiskHistoricalSummary(
            closed_net_profit=closed_net_profit,
            open_unrealized_pnl=open_unrealized_pnl,
            combined_realized_unrealized_pnl=closed_net_profit + open_unrealized_pnl,
            best_closed_profit=max((row["net_profit"] for row in closed_rows), default=None),
            worst_open_unrealized_loss=min(open_losses, default=None),
            avg_holding_time_closed_seconds=self._average(closed_durations),
            avg_age_open_seconds=self._average(open_ages),
        )

    def _would_timeout_count(self, rows: list[dict], max_age_seconds: int) -> int:
        count = 0
        for row in rows:
            duration = self._duration_seconds(row) if row["status"] == "CLOSED" else self._age_seconds(row)
            if duration is not None and duration >= max_age_seconds:
                count += 1
        return count

    @staticmethod
    def _recommend(
        open_cycles: list[OpenCycleExitRisk],
        max_holding_results: list[MaxHoldingSimulationResult],
    ) -> str:
        if not open_cycles:
            return "no stop yet: no open cycles to protect."
        worst_adverse = max((item.adverse_move_percent for item in open_cycles), default=0.0)
        four_hour_timeouts = next(
            (item.would_timeout_count for item in max_holding_results if item.max_age_seconds == 4 * 60 * 60),
            0,
        )
        if worst_adverse >= 0.03:
            return "hard stop: at least one open cycle exceeds 0.03% adverse movement."
        if worst_adverse >= 0.01:
            return "soft stop: adverse movement is visible; test 0.01%-0.02% stops before changing strategy."
        if four_hour_timeouts:
            return "max holding needed: at least one cycle exceeds 4 hours."
        return "no stop yet: current open-cycle adverse movement is below tested thresholds."

    @staticmethod
    def _adverse_move_percent(direction: str, open_price: float, current_price: float) -> float:
        if open_price == 0:
            return 0.0
        if direction == "BUY_USDC":
            adverse = max(0.0, open_price - current_price)
        elif direction == "SELL_USDC":
            adverse = max(0.0, current_price - open_price)
        else:
            adverse = 0.0
        return adverse / open_price * 100.0

    @staticmethod
    def _distance_to_target(direction: str, current_price: float, target_price: float) -> float:
        if direction == "BUY_USDC":
            return target_price - current_price
        if direction == "SELL_USDC":
            return current_price - target_price
        return target_price - current_price

    @staticmethod
    def _age_seconds(row: dict) -> float:
        opened_at = datetime.fromisoformat(row["opened_at"])
        now = datetime.now(tz=opened_at.tzinfo) if opened_at.tzinfo else datetime.now()
        return max(0.0, (now - opened_at).total_seconds())

    @staticmethod
    def _duration_seconds(row: dict) -> float | None:
        if not row.get("closed_at"):
            return None
        opened_at = datetime.fromisoformat(row["opened_at"])
        closed_at = datetime.fromisoformat(row["closed_at"])
        return max(0.0, (closed_at - opened_at).total_seconds())

    @staticmethod
    def _average(values: list[float]) -> float | None:
        return sum(values) / len(values) if values else None
