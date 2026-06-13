from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager
from strategy.profile_decision_engine import SMALL_TARGET_MULTIPLIER
from trading.fee_engine import FeeEngine


TREND_LOOKBACK = timedelta(hours=1)
TREND_FLAT_THRESHOLD = 0.00005
TREND_FILTER_PROFILES = (
    "no_trend_filter",
    "block_buy_if_1h_down",
    "block_sell_if_1h_up",
    "require_entry_aligned_with_1h",
)


@dataclass(frozen=True)
class TrendSnapshot:
    timestamp: datetime
    timestamp_text: str
    price: float
    work_position: float
    spread: float
    market_regime: str
    micro_trend: str
    volatility_regime: str
    market_health_score: float
    market_health_status: str


@dataclass(frozen=True)
class OpenCycleTrendDiagnostic:
    db_id: int
    direction: str
    opened_at: str
    open_price: float
    current_price: float
    target_price: float
    unrealized_pnl: float
    entry_1h_trend: str
    current_1h_trend: str
    entry_aligned_with_1h: bool
    entry_against_1h: bool


@dataclass(frozen=True)
class TrendCycleStats:
    total_cycles: int
    aligned_cycles: int
    against_trend_cycles: int
    win_rate_aligned: float
    win_rate_against_trend: float
    net_profit_aligned: float
    net_profit_against_trend: float


@dataclass(frozen=True)
class TrendAlignmentReport:
    profile: str
    current_price: float
    open_cycles: list[OpenCycleTrendDiagnostic]
    cycle_stats: TrendCycleStats


@dataclass(frozen=True)
class TrendFilterSimulationResult:
    name: str
    candidates_total: int
    candidates_kept: int
    candidates_blocked: int
    would_block_current_bad_buy_cycle: bool
    estimated_pnl_impact: float
    recommendation: str


@dataclass(frozen=True)
class TrendFilterSimulationReport:
    profile: str
    current_bad_buy_cycle_db_id: int | None
    results: list[TrendFilterSimulationResult]


class TrendAlignmentDiagnosticsEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.database = database
        self.config = config
        self.fee_engine = FeeEngine(config)

    def build_alignment_report(self, *, profile: str, current_price: float) -> TrendAlignmentReport:
        snapshots = self._load_snapshots()
        return TrendAlignmentReport(
            profile=profile,
            current_price=current_price,
            open_cycles=self._open_cycle_diagnostics(profile, current_price, snapshots),
            cycle_stats=self._cycle_stats(profile, snapshots),
        )

    def build_filter_simulation(self, *, profile: str) -> TrendFilterSimulationReport:
        snapshots = self._load_snapshots()
        candidates = [
            (snapshot, self._entry_direction(snapshot, profile), self._trend_at(snapshots, snapshot.timestamp))
            for snapshot in snapshots
        ]
        candidates = [
            item for item in candidates
            if item[1] in {"BUY_USDC", "SELL_USDC"}
        ]
        current_bad_buy = self._current_bad_buy_cycle(profile)
        results = [
            self._simulate_filter(name, candidates, current_bad_buy, profile)
            for name in TREND_FILTER_PROFILES
        ]
        return TrendFilterSimulationReport(
            profile=profile,
            current_bad_buy_cycle_db_id=current_bad_buy["db_id"] if current_bad_buy else None,
            results=results,
        )

    def _open_cycle_diagnostics(
        self,
        profile: str,
        current_price: float,
        snapshots: list[TrendSnapshot],
    ) -> list[OpenCycleTrendDiagnostic]:
        items: list[OpenCycleTrendDiagnostic] = []
        for row in self._load_open_cycle_rows(profile):
            (
                db_id,
                _timestamp,
                _cycle_id,
                _strategy_profile,
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
            direction = clean_display_text(direction)
            opened_at_text = clean_display_text(opened_at)
            opened_at_dt = datetime.fromisoformat(opened_at_text)
            open_price = float(open_price)
            close_price = float(close_price)
            profit = self.fee_engine.calculate_profit(
                direction=direction,
                open_price=open_price,
                close_price=current_price,
                quantity=float(quantity),
                use_taker_fee=True,
            )
            entry_trend = self._trend_at(snapshots, opened_at_dt)
            current_trend = self._trend_at(snapshots, snapshots[-1].timestamp) if snapshots else "UNKNOWN"
            items.append(
                OpenCycleTrendDiagnostic(
                    db_id=int(db_id),
                    direction=direction,
                    opened_at=opened_at_text,
                    open_price=open_price,
                    current_price=current_price,
                    target_price=close_price,
                    unrealized_pnl=profit.net_profit,
                    entry_1h_trend=entry_trend,
                    current_1h_trend=current_trend,
                    entry_aligned_with_1h=self._is_aligned(direction, entry_trend),
                    entry_against_1h=self._is_against(direction, entry_trend),
                )
            )
        return items

    def _cycle_stats(self, profile: str, snapshots: list[TrendSnapshot]) -> TrendCycleStats:
        rows = self._load_cycle_rows(profile)
        aligned = []
        against = []
        for row in rows:
            (
                _db_id,
                _timestamp,
                _cycle_id,
                _strategy_profile,
                direction,
                status,
                _open_price,
                _close_price,
                _quantity,
                _open_fee,
                _close_fee,
                _gross_profit,
                net_profit,
                opened_at,
                _closed_at,
            ) = row
            trend = self._trend_at(snapshots, datetime.fromisoformat(clean_display_text(opened_at)))
            item = {"status": clean_display_text(status), "net_profit": float(net_profit)}
            if self._is_aligned(clean_display_text(direction), trend):
                aligned.append(item)
            elif self._is_against(clean_display_text(direction), trend):
                against.append(item)

        return TrendCycleStats(
            total_cycles=len(rows),
            aligned_cycles=len(aligned),
            against_trend_cycles=len(against),
            win_rate_aligned=self._win_rate(aligned),
            win_rate_against_trend=self._win_rate(against),
            net_profit_aligned=sum(item["net_profit"] for item in aligned if item["status"] == "CLOSED"),
            net_profit_against_trend=sum(item["net_profit"] for item in against if item["status"] == "CLOSED"),
        )

    def _simulate_filter(
        self,
        name: str,
        candidates: list[tuple[TrendSnapshot, str, str]],
        current_bad_buy: dict | None,
        profile: str,
    ) -> TrendFilterSimulationResult:
        kept = [
            item for item in candidates
            if self._trend_filter_pass(name, direction=item[1], trend=item[2])
        ]
        blocked = len(candidates) - len(kept)
        blocked_pnl = [
            self._estimate_candidate_pnl(snapshot, direction, profile=profile)
            for snapshot, direction, trend in candidates
            if not self._trend_filter_pass(name, direction=direction, trend=trend)
        ]
        would_block_bad_buy = False
        if current_bad_buy is not None:
            would_block_bad_buy = not self._trend_filter_pass(
                name,
                direction=current_bad_buy["direction"],
                trend=current_bad_buy["entry_trend"],
            )

        return TrendFilterSimulationResult(
            name=name,
            candidates_total=len(candidates),
            candidates_kept=len(kept),
            candidates_blocked=blocked,
            would_block_current_bad_buy_cycle=would_block_bad_buy,
            estimated_pnl_impact=-sum(blocked_pnl),
            recommendation=self._recommendation(name, len(candidates), len(kept), would_block_bad_buy),
        )

    def _current_bad_buy_cycle(self, profile: str) -> dict | None:
        snapshots = self._load_snapshots()
        rows = self._load_open_cycle_rows(profile)
        bad_buys = []
        for row in rows:
            db_id, *_rest = row
            direction = clean_display_text(row[4])
            net_profit = float(row[12])
            opened_at = datetime.fromisoformat(clean_display_text(row[13]))
            if direction == "BUY_USDC" and net_profit <= 0:
                bad_buys.append({
                    "db_id": int(db_id),
                    "profile": profile,
                    "direction": direction,
                    "entry_trend": self._trend_at(snapshots, opened_at),
                })
        return bad_buys[0] if bad_buys else None

    def _load_cycle_rows(self, profile: str) -> list[tuple]:
        with self.database.connect() as conn:
            return conn.execute(
                """
                SELECT id, timestamp, cycle_id, strategy_profile, direction, status,
                       open_price, close_price, quantity, open_fee, close_fee,
                       gross_profit, net_profit, opened_at, closed_at
                FROM paper_cycles
                WHERE strategy_profile = ?
                ORDER BY opened_at ASC
                """,
                (profile,),
            ).fetchall()

    def _load_open_cycle_rows(self, profile: str) -> list[tuple]:
        return [row for row in self.database.load_open_paper_cycles(limit=1000) if row[3] == profile]

    def _load_snapshots(self) -> list[TrendSnapshot]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT timestamp, price, work_position, spread, market_regime,
                       micro_trend, volatility_regime, market_health_score,
                       market_health_status
                FROM market_snapshots
                ORDER BY timestamp ASC
                """
            ).fetchall()

        return [
            TrendSnapshot(
                timestamp=self._parse_timestamp(timestamp),
                timestamp_text=clean_display_text(timestamp),
                price=float(price or 0.0),
                work_position=float(work_position or 0.0),
                spread=float(spread or 0.0),
                market_regime=self._text(market_regime),
                micro_trend=self._text(micro_trend),
                volatility_regime=self._text(volatility_regime),
                market_health_score=float(market_health_score or 0.0),
                market_health_status=self._text(market_health_status),
            )
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

    def _trend_at(self, snapshots: list[TrendSnapshot], timestamp: datetime) -> str:
        if timestamp.tzinfo is not None:
            timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)
        current = self._snapshot_at_or_before(snapshots, timestamp)
        previous = self._snapshot_at_or_before(snapshots, timestamp - TREND_LOOKBACK)
        if current is None or previous is None:
            return "UNKNOWN"
        delta = current.price - previous.price
        if delta > TREND_FLAT_THRESHOLD:
            return "UP"
        if delta < -TREND_FLAT_THRESHOLD:
            return "DOWN"
        return "FLAT"

    @staticmethod
    def _snapshot_at_or_before(snapshots: list[TrendSnapshot], timestamp: datetime) -> TrendSnapshot | None:
        selected = None
        for snapshot in snapshots:
            if snapshot.timestamp <= timestamp:
                selected = snapshot
            else:
                break
        return selected

    def _entry_direction(self, snapshot: TrendSnapshot, profile: str) -> str:
        buy_zone = 25.0 if profile in {"mean_reversion_v2", "mean_reversion_v2_small_target"} else self.config.buy_zone_max
        sell_zone = 75.0 if profile in {"mean_reversion_v2", "mean_reversion_v2_small_target"} else self.config.sell_zone_min
        if not self._safety_filters_pass(snapshot):
            return "WAIT"
        if snapshot.work_position <= buy_zone and snapshot.micro_trend == "BUY_DOMINANT":
            return "BUY_USDC"
        if snapshot.work_position >= sell_zone and snapshot.micro_trend == "SELL_DOMINANT":
            return "SELL_USDC"
        return "WAIT"

    def _safety_filters_pass(self, snapshot: TrendSnapshot) -> bool:
        return (
            0.0 < snapshot.spread <= self.config.max_allowed_spread
            and snapshot.market_health_score >= self.config.min_market_health_score
            and snapshot.market_health_status != "UNHEALTHY"
            and snapshot.market_regime != "ABNORMAL"
            and snapshot.volatility_regime != "EXTREME"
        )

    def _estimate_candidate_pnl(self, snapshot: TrendSnapshot, direction: str, profile: str) -> float:
        target_profit = self.config.target_profit
        if profile == "mean_reversion_v2_small_target":
            target_profit = self.config.target_profit * SMALL_TARGET_MULTIPLIER
        target_price = snapshot.price * (1 + target_profit) if direction == "BUY_USDC" else snapshot.price * (1 - target_profit)
        quantity = (self.config.backtest_initial_usdt * self.config.trade_size_percent) / snapshot.price
        return self.fee_engine.calculate_profit(
            direction=direction,
            open_price=snapshot.price,
            close_price=target_price,
            quantity=quantity,
            use_taker_fee=True,
        ).net_profit

    @staticmethod
    def _trend_filter_pass(name: str, *, direction: str, trend: str) -> bool:
        if name == "no_trend_filter":
            return True
        if name == "block_buy_if_1h_down":
            return not (direction == "BUY_USDC" and trend == "DOWN")
        if name == "block_sell_if_1h_up":
            return not (direction == "SELL_USDC" and trend == "UP")
        if name == "require_entry_aligned_with_1h":
            return TrendAlignmentDiagnosticsEngine._is_aligned(direction, trend)
        return True

    @staticmethod
    def _is_aligned(direction: str, trend: str) -> bool:
        return (direction == "BUY_USDC" and trend == "UP") or (direction == "SELL_USDC" and trend == "DOWN")

    @staticmethod
    def _is_against(direction: str, trend: str) -> bool:
        return (direction == "BUY_USDC" and trend == "DOWN") or (direction == "SELL_USDC" and trend == "UP")

    @staticmethod
    def _win_rate(items: list[dict]) -> float:
        closed = [item for item in items if item["status"] == "CLOSED"]
        if not closed:
            return 0.0
        return sum(1 for item in closed if item["net_profit"] > 0) / len(closed)

    @staticmethod
    def _recommendation(name: str, total: int, kept: int, would_block_bad_buy: bool) -> str:
        if total == 0:
            return "No candidate data available."
        if name == "require_entry_aligned_with_1h" and kept == 0:
            return "Too strict for current sample."
        if would_block_bad_buy:
            return "Promising: blocks the current adverse BUY cycle."
        return "Diagnostic only; compare with realized paper outcomes."

    @staticmethod
    def _parse_timestamp(value) -> datetime:
        parsed = datetime.fromisoformat(clean_display_text(value))
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed

    @staticmethod
    def _text(value) -> str:
        return clean_display_text(value or "UNKNOWN").strip().upper()
