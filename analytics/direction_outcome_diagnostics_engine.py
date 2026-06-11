from __future__ import annotations

from dataclasses import dataclass

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager
from trading.fee_engine import FeeEngine


SUPPORTED_DIRECTION_OUTCOME_PROFILES = ("mean_reversion_v1", "mean_reversion_v2")
DEFAULT_OUTCOME_HORIZONS = (1, 3, 5, 10)


@dataclass(frozen=True)
class OpenCycleDirectionOutcome:
    db_id: int
    cycle_id: int
    profile: str
    direction: str
    opened_at: str
    age_seconds: float
    open_price: float
    target_price: float
    current_price: float
    moved_expected_direction: bool
    unrealized_pnl: float
    distance_from_open: float
    distance_to_target: float


@dataclass(frozen=True)
class OpenCycleDirectionSummary:
    buy_cycles_count: int
    sell_cycles_count: int
    moved_expected_direction_count: int
    moved_against_direction_count: int
    avg_unrealized_pnl: float | None
    worst_unrealized_pnl: float | None
    best_unrealized_pnl: float | None


@dataclass(frozen=True)
class HistoricalDirectionOutcome:
    horizon: int
    entry_signals_count: int
    moved_expected_direction_count: int
    moved_expected_direction_rate: float
    buy_signals_count: int
    sell_signals_count: int


@dataclass(frozen=True)
class DirectionOutcomeDiagnosticsReport:
    profile: str
    current_price: float
    open_cycles: list[OpenCycleDirectionOutcome]
    open_summary: OpenCycleDirectionSummary
    historical_outcomes: list[HistoricalDirectionOutcome]


class DirectionOutcomeDiagnosticsEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.database = database
        self.config = config
        self.fee_engine = FeeEngine(config)

    def build_report(
        self,
        *,
        current_price: float,
        profile: str = "mean_reversion_v2",
        horizons: tuple[int, ...] = DEFAULT_OUTCOME_HORIZONS,
    ) -> DirectionOutcomeDiagnosticsReport:
        if profile not in SUPPORTED_DIRECTION_OUTCOME_PROFILES:
            supported = ", ".join(SUPPORTED_DIRECTION_OUTCOME_PROFILES)
            raise ValueError(f"Unsupported direction outcome profile: {profile}. Supported: {supported}")

        open_cycles = self._build_open_cycle_outcomes(current_price, profile)
        return DirectionOutcomeDiagnosticsReport(
            profile=profile,
            current_price=current_price,
            open_cycles=open_cycles,
            open_summary=self._summarize_open_cycles(open_cycles),
            historical_outcomes=self._build_historical_outcomes(profile, horizons),
        )

    def _build_open_cycle_outcomes(
        self,
        current_price: float,
        profile: str,
    ) -> list[OpenCycleDirectionOutcome]:
        rows = self.database.load_open_paper_cycles(limit=1000)
        outcomes: list[OpenCycleDirectionOutcome] = []
        for row in rows:
            (
                db_id,
                _timestamp,
                cycle_id,
                strategy_profile,
                direction,
                _status,
                open_price,
                close_price,
                quantity,
                _open_fee,
                _close_fee,
                _gross_profit,
                _net_profit,
                opened_at,
                _closed_at,
            ) = row
            strategy_profile = clean_display_text(strategy_profile or "UNKNOWN")
            if strategy_profile != profile:
                continue

            direction = clean_display_text(direction)
            open_price = float(open_price)
            target_price = float(close_price)
            quantity = float(quantity)
            profit = self.fee_engine.calculate_profit(
                direction=direction,
                open_price=open_price,
                close_price=current_price,
                quantity=quantity,
                use_taker_fee=True,
            )
            distance_from_open = self._distance_from_open(direction, current_price, open_price)
            outcomes.append(
                OpenCycleDirectionOutcome(
                    db_id=int(db_id),
                    cycle_id=int(cycle_id),
                    profile=strategy_profile,
                    direction=direction,
                    opened_at=clean_display_text(opened_at),
                    age_seconds=self._age_seconds(clean_display_text(opened_at)),
                    open_price=open_price,
                    target_price=target_price,
                    current_price=current_price,
                    moved_expected_direction=distance_from_open > 0,
                    unrealized_pnl=profit.net_profit,
                    distance_from_open=distance_from_open,
                    distance_to_target=self._distance_to_target(direction, current_price, target_price),
                )
            )
        return outcomes

    def _build_historical_outcomes(
        self,
        profile: str,
        horizons: tuple[int, ...],
    ) -> list[HistoricalDirectionOutcome]:
        rows = self._load_snapshot_rows()
        entry_rows = [
            (index, row)
            for index, row in enumerate(rows)
            if self._entry_direction(row, profile) in {"BUY_USDC", "SELL_USDC"}
        ]

        outcomes: list[HistoricalDirectionOutcome] = []
        for horizon in horizons:
            evaluated = 0
            moved_expected = 0
            buy_count = 0
            sell_count = 0
            for index, row in entry_rows:
                future_index = index + horizon
                if future_index >= len(rows):
                    continue

                action = self._entry_direction(row, profile)
                if action == "BUY_USDC":
                    buy_count += 1
                elif action == "SELL_USDC":
                    sell_count += 1
                else:
                    continue

                evaluated += 1
                future_price = rows[future_index]["price"]
                if self._price_moved_expected(action, row["price"], future_price):
                    moved_expected += 1

            outcomes.append(
                HistoricalDirectionOutcome(
                    horizon=horizon,
                    entry_signals_count=evaluated,
                    moved_expected_direction_count=moved_expected,
                    moved_expected_direction_rate=moved_expected / evaluated if evaluated else 0.0,
                    buy_signals_count=buy_count,
                    sell_signals_count=sell_count,
                )
            )
        return outcomes

    def _entry_direction(self, row: dict, profile: str) -> str:
        buy_zone_max = 25.0 if profile == "mean_reversion_v2" else self.config.buy_zone_max
        sell_zone_min = 75.0 if profile == "mean_reversion_v2" else self.config.sell_zone_min

        if not (0.0 < row["spread"] <= self.config.max_allowed_spread):
            return "WAIT"
        if (
            row["market_health_score"] < self.config.min_market_health_score
            or row["market_health_status"] == "UNHEALTHY"
        ):
            return "WAIT"
        if row["market_regime"] == "ABNORMAL" or row["volatility_regime"] == "EXTREME":
            return "WAIT"

        if row["work_position"] <= buy_zone_max and row["micro_trend"] == "BUY_DOMINANT":
            return "BUY_USDC"
        if row["work_position"] >= sell_zone_min and row["micro_trend"] == "SELL_DOMINANT":
            return "SELL_USDC"
        return "WAIT"

    def _load_snapshot_rows(self) -> list[dict]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    timestamp,
                    price,
                    work_position,
                    spread,
                    market_regime,
                    micro_trend,
                    volatility_regime,
                    market_health_score,
                    market_health_status
                FROM market_snapshots
                ORDER BY timestamp ASC
                """
            ).fetchall()

        return [
            {
                "timestamp": clean_display_text(timestamp),
                "price": self._float(price),
                "work_position": self._float(work_position),
                "spread": self._float(spread),
                "market_regime": self._text(market_regime),
                "micro_trend": self._text(micro_trend),
                "volatility_regime": self._text(volatility_regime),
                "market_health_score": self._float(market_health_score),
                "market_health_status": self._text(market_health_status),
            }
            for (
                timestamp,
                price,
                work_position,
                spread,
                market_regime,
                micro_trend,
                volatility_regime,
                market_health_score,
                market_health_status,
            ) in rows
        ]

    @staticmethod
    def _summarize_open_cycles(open_cycles: list[OpenCycleDirectionOutcome]) -> OpenCycleDirectionSummary:
        pnl_values = [item.unrealized_pnl for item in open_cycles]
        moved_expected = sum(1 for item in open_cycles if item.moved_expected_direction)
        return OpenCycleDirectionSummary(
            buy_cycles_count=sum(1 for item in open_cycles if item.direction == "BUY_USDC"),
            sell_cycles_count=sum(1 for item in open_cycles if item.direction == "SELL_USDC"),
            moved_expected_direction_count=moved_expected,
            moved_against_direction_count=len(open_cycles) - moved_expected,
            avg_unrealized_pnl=sum(pnl_values) / len(pnl_values) if pnl_values else None,
            worst_unrealized_pnl=min(pnl_values) if pnl_values else None,
            best_unrealized_pnl=max(pnl_values) if pnl_values else None,
        )

    @staticmethod
    def _distance_from_open(direction: str, current_price: float, open_price: float) -> float:
        if direction == "BUY_USDC":
            return current_price - open_price
        if direction == "SELL_USDC":
            return open_price - current_price
        return current_price - open_price

    @staticmethod
    def _distance_to_target(direction: str, current_price: float, target_price: float) -> float:
        if direction == "BUY_USDC":
            return target_price - current_price
        if direction == "SELL_USDC":
            return current_price - target_price
        return target_price - current_price

    @staticmethod
    def _price_moved_expected(action: str, entry_price: float, future_price: float) -> bool:
        if action == "BUY_USDC":
            return future_price > entry_price
        if action == "SELL_USDC":
            return future_price < entry_price
        return False

    @staticmethod
    def _age_seconds(opened_at: str) -> float:
        from datetime import datetime

        opened_at_dt = datetime.fromisoformat(opened_at)
        now = datetime.now(tz=opened_at_dt.tzinfo) if opened_at_dt.tzinfo else datetime.now()
        return max(0.0, (now - opened_at_dt).total_seconds())

    @staticmethod
    def _text(value) -> str:
        return clean_display_text(value or "UNKNOWN").strip().upper()

    @staticmethod
    def _float(value) -> float:
        return float(value or 0.0)
