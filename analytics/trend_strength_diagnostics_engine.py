from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.text_encoding import clean_display_text
from config.config_manager import BotConfig
from storage.database_manager import DatabaseManager
from strategy.profile_decision_engine import SMALL_TARGET_MULTIPLIER
from trading.fee_engine import FeeEngine


TREND_STRENGTH_LOOKBACK = timedelta(hours=1)
TREND_STRENGTH_HIT_HORIZON = 30
TREND_STRENGTH_FLAT_THRESHOLD = 0.00005
TREND_STRENGTH_RULES = (
    ("flat_as_down_0_005_percent", "DOWN", -0.00005),
    ("flat_as_down_0_01_percent", "DOWN", -0.00010),
    ("flat_as_up_0_005_percent", "UP", 0.00005),
    ("flat_as_up_0_01_percent", "UP", 0.00010),
)


@dataclass(frozen=True)
class TrendStrengthSnapshot:
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
class TrendStrengthItem:
    source: str
    db_id: int | None
    timestamp: str
    direction: str
    entry_price: float
    comparison_price: float | None
    trend_label: str
    one_hour_change: float | None
    one_hour_change_percent: float | None
    one_hour_slope: float | None
    rolling_min: float | None
    rolling_max: float | None
    position_inside_range: float | None
    near_top_of_range: bool
    near_bottom_of_range: bool
    outcome: str


@dataclass(frozen=True)
class TrendStrengthRuleSimulation:
    name: str
    candidates_total: int
    candidates_blocked: int
    candidates_kept: int
    bad_open_cycle_blocked: bool
    hit_target_count: int
    hit_target_rate: float
    recommendation_score: float


@dataclass(frozen=True)
class TrendStrengthDiagnosticsReport:
    profile: str
    candidates: list[TrendStrengthItem]
    open_cycles: list[TrendStrengthItem]
    simulations: list[TrendStrengthRuleSimulation]


class TrendStrengthDiagnosticsEngine:
    def __init__(self, database: DatabaseManager, config: BotConfig) -> None:
        self.database = database
        self.config = config
        self.fee_engine = FeeEngine(config)

    def build_report(self, *, profile: str) -> TrendStrengthDiagnosticsReport:
        snapshots = self._load_snapshots()
        candidates = self._candidate_items(profile, snapshots)
        open_cycles = self._open_cycle_items(profile, snapshots)
        return TrendStrengthDiagnosticsReport(
            profile=profile,
            candidates=[item for _index, item in candidates],
            open_cycles=open_cycles,
            simulations=[
                self._simulate_rule(rule_name, relabel_to, threshold, profile, snapshots, candidates, open_cycles)
                for rule_name, relabel_to, threshold in TREND_STRENGTH_RULES
            ],
        )

    def _candidate_items(
        self,
        profile: str,
        snapshots: list[TrendStrengthSnapshot],
    ) -> list[tuple[int, TrendStrengthItem]]:
        items: list[tuple[int, TrendStrengthItem]] = []
        for index, snapshot in enumerate(snapshots):
            direction = self._entry_direction(snapshot, profile)
            if direction not in {"BUY_USDC", "SELL_USDC"}:
                continue
            future = snapshots[index + 1:index + 1 + TREND_STRENGTH_HIT_HORIZON]
            comparison_price = future[-1].price if future else None
            target_price = self._target_price(snapshot.price, direction, profile)
            outcome = "not hit"
            if self._target_hit(direction, target_price, future):
                outcome = "hit target"
            items.append(
                (
                    index,
                    self._build_item(
                        source="candidate",
                        db_id=None,
                        timestamp=snapshot.timestamp,
                        timestamp_text=snapshot.timestamp_text,
                        direction=direction,
                        entry_price=snapshot.price,
                        comparison_price=comparison_price,
                        outcome=outcome,
                        snapshots=snapshots,
                    ),
                )
            )
        return items

    def _open_cycle_items(
        self,
        profile: str,
        snapshots: list[TrendStrengthSnapshot],
    ) -> list[TrendStrengthItem]:
        if not snapshots:
            return []
        latest_price = snapshots[-1].price
        items: list[TrendStrengthItem] = []
        for row in self.database.load_open_paper_cycles(limit=1000):
            (
                db_id,
                _timestamp,
                _cycle_id,
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
            if clean_display_text(strategy_profile or "") != profile:
                continue
            direction = clean_display_text(direction)
            opened_at_text = clean_display_text(opened_at)
            opened_at_dt = self._parse_timestamp(opened_at_text)
            profit = self.fee_engine.calculate_profit(
                direction=direction,
                open_price=float(open_price),
                close_price=latest_price,
                quantity=float(quantity),
                use_taker_fee=True,
            )
            outcome = "open loss" if profit.net_profit < 0 else "open profit"
            if self._close_condition_met(direction, latest_price, float(close_price)):
                outcome = "hit target"
            items.append(
                self._build_item(
                    source="open_cycle",
                    db_id=int(db_id),
                    timestamp=opened_at_dt,
                    timestamp_text=opened_at_text,
                    direction=direction,
                    entry_price=float(open_price),
                    comparison_price=latest_price,
                    outcome=outcome,
                    snapshots=snapshots,
                )
            )
        return items

    def _build_item(
        self,
        *,
        source: str,
        db_id: int | None,
        timestamp: datetime,
        timestamp_text: str,
        direction: str,
        entry_price: float,
        comparison_price: float | None,
        outcome: str,
        snapshots: list[TrendStrengthSnapshot],
    ) -> TrendStrengthItem:
        metrics = self._trend_metrics(snapshots, timestamp)
        return TrendStrengthItem(
            source=source,
            db_id=db_id,
            timestamp=timestamp_text,
            direction=direction,
            entry_price=entry_price,
            comparison_price=comparison_price,
            trend_label=metrics["label"],
            one_hour_change=metrics["change"],
            one_hour_change_percent=metrics["change_percent"],
            one_hour_slope=metrics["slope"],
            rolling_min=metrics["rolling_min"],
            rolling_max=metrics["rolling_max"],
            position_inside_range=metrics["position_inside_range"],
            near_top_of_range=bool(metrics["near_top_of_range"]),
            near_bottom_of_range=bool(metrics["near_bottom_of_range"]),
            outcome=outcome,
        )

    def _simulate_rule(
        self,
        name: str,
        relabel_to: str,
        threshold: float,
        profile: str,
        snapshots: list[TrendStrengthSnapshot],
        candidates: list[tuple[int, TrendStrengthItem]],
        open_cycles: list[TrendStrengthItem],
    ) -> TrendStrengthRuleSimulation:
        kept: list[tuple[int, TrendStrengthItem]] = []
        blocked: list[tuple[int, TrendStrengthItem]] = []
        for item in candidates:
            _index, candidate = item
            trend = self._relabel_flat_trend(candidate, relabel_to, threshold)
            if self._is_against(candidate.direction, trend):
                blocked.append(item)
            else:
                kept.append(item)

        hit_count = sum(
            1
            for index, candidate in kept
            if self._target_hit(
                candidate.direction,
                self._target_price(candidate.entry_price, candidate.direction, profile),
                snapshots[index + 1:index + 1 + TREND_STRENGTH_HIT_HORIZON],
            )
        )
        bad_blocked = any(
            self._is_bad_buy(item)
            and self._is_against(item.direction, self._relabel_flat_trend(item, relabel_to, threshold))
            for item in open_cycles
        )
        hit_rate = hit_count / len(kept) if kept else 0.0
        return TrendStrengthRuleSimulation(
            name=name,
            candidates_total=len(candidates),
            candidates_blocked=len(blocked),
            candidates_kept=len(kept),
            bad_open_cycle_blocked=bad_blocked,
            hit_target_count=hit_count,
            hit_target_rate=hit_rate,
            recommendation_score=self._recommendation_score(
                total=len(candidates),
                kept=len(kept),
                hit_target_rate=hit_rate,
                bad_open_cycle_blocked=bad_blocked,
            ),
        )

    def _trend_metrics(self, snapshots: list[TrendStrengthSnapshot], timestamp: datetime) -> dict:
        current = self._snapshot_at_or_before(snapshots, timestamp)
        previous = self._snapshot_at_or_before(snapshots, timestamp - TREND_STRENGTH_LOOKBACK)
        if current is None or previous is None or previous.price <= 0:
            return {
                "label": "UNKNOWN",
                "change": None,
                "change_percent": None,
                "slope": None,
                "rolling_min": None,
                "rolling_max": None,
                "position_inside_range": None,
                "near_top_of_range": False,
                "near_bottom_of_range": False,
            }

        window = [
            snapshot.price
            for snapshot in snapshots
            if timestamp - TREND_STRENGTH_LOOKBACK <= snapshot.timestamp <= timestamp
        ]
        rolling_min = min(window) if window else current.price
        rolling_max = max(window) if window else current.price
        change = current.price - previous.price
        change_percent = change / previous.price
        slope = change / (TREND_STRENGTH_LOOKBACK.total_seconds() / 60.0)
        label = "FLAT"
        if change > TREND_STRENGTH_FLAT_THRESHOLD:
            label = "UP"
        elif change < -TREND_STRENGTH_FLAT_THRESHOLD:
            label = "DOWN"

        range_width = rolling_max - rolling_min
        position = ((current.price - rolling_min) / range_width) if range_width > 0 else 0.5
        return {
            "label": label,
            "change": change,
            "change_percent": change_percent,
            "slope": slope,
            "rolling_min": rolling_min,
            "rolling_max": rolling_max,
            "position_inside_range": position,
            "near_top_of_range": position >= 0.8,
            "near_bottom_of_range": position <= 0.2,
        }

    def _entry_direction(self, snapshot: TrendStrengthSnapshot, profile: str) -> str:
        buy_zone = 25.0 if profile in {"mean_reversion_v2", "mean_reversion_v2_small_target"} else self.config.buy_zone_max
        sell_zone = 75.0 if profile in {"mean_reversion_v2", "mean_reversion_v2_small_target"} else self.config.sell_zone_min
        if not self._safety_filters_pass(snapshot):
            return "WAIT"
        if snapshot.work_position <= buy_zone and snapshot.micro_trend == "BUY_DOMINANT":
            return "BUY_USDC"
        if snapshot.work_position >= sell_zone and snapshot.micro_trend == "SELL_DOMINANT":
            return "SELL_USDC"
        return "WAIT"

    def _safety_filters_pass(self, snapshot: TrendStrengthSnapshot) -> bool:
        return (
            0.0 < snapshot.spread <= self.config.max_allowed_spread
            and snapshot.market_health_score >= self.config.min_market_health_score
            and snapshot.market_health_status != "UNHEALTHY"
            and snapshot.market_regime != "ABNORMAL"
            and snapshot.volatility_regime != "EXTREME"
        )

    def _target_price(self, entry_price: float, direction: str, profile: str) -> float:
        target_profit = self.config.target_profit
        if profile == "mean_reversion_v2_small_target":
            target_profit = self.config.target_profit * SMALL_TARGET_MULTIPLIER
        if direction == "BUY_USDC":
            return entry_price * (1 + target_profit)
        return entry_price * (1 - target_profit)

    @staticmethod
    def _target_hit(direction: str, target_price: float, future: list[TrendStrengthSnapshot]) -> bool:
        if direction == "BUY_USDC":
            return any(snapshot.price >= target_price for snapshot in future)
        if direction == "SELL_USDC":
            return any(snapshot.price <= target_price for snapshot in future)
        return False

    @staticmethod
    def _close_condition_met(direction: str, current_price: float, target_price: float) -> bool:
        if direction == "BUY_USDC":
            return current_price >= target_price
        if direction == "SELL_USDC":
            return current_price <= target_price
        return False

    @staticmethod
    def _relabel_flat_trend(item: TrendStrengthItem, relabel_to: str, threshold: float) -> str:
        if item.trend_label != "FLAT" or item.one_hour_change_percent is None:
            return item.trend_label
        if relabel_to == "DOWN" and item.one_hour_change_percent < threshold:
            return "DOWN"
        if relabel_to == "UP" and item.one_hour_change_percent > threshold:
            return "UP"
        return item.trend_label

    @staticmethod
    def _is_against(direction: str, trend: str) -> bool:
        return (direction == "BUY_USDC" and trend == "DOWN") or (direction == "SELL_USDC" and trend == "UP")

    @staticmethod
    def _is_bad_buy(item: TrendStrengthItem) -> bool:
        return item.source == "open_cycle" and item.direction == "BUY_USDC" and item.outcome == "open loss"

    @staticmethod
    def _recommendation_score(
        *,
        total: int,
        kept: int,
        hit_target_rate: float,
        bad_open_cycle_blocked: bool,
    ) -> float:
        if total == 0:
            return 0.0
        kept_rate = kept / total
        block_bonus = 25.0 if bad_open_cycle_blocked else 0.0
        score = (hit_target_rate * 55.0) + (kept_rate * 20.0) + block_bonus
        return round(max(0.0, min(100.0, score)), 2)

    def _load_snapshots(self) -> list[TrendStrengthSnapshot]:
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
            TrendStrengthSnapshot(
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

    @staticmethod
    def _snapshot_at_or_before(
        snapshots: list[TrendStrengthSnapshot],
        timestamp: datetime,
    ) -> TrendStrengthSnapshot | None:
        if timestamp.tzinfo is not None:
            timestamp = timestamp.astimezone(timezone.utc).replace(tzinfo=None)
        selected = None
        for snapshot in snapshots:
            if snapshot.timestamp <= timestamp:
                selected = snapshot
            else:
                break
        return selected

    @staticmethod
    def _parse_timestamp(value) -> datetime:
        parsed = datetime.fromisoformat(clean_display_text(value))
        if parsed.tzinfo is not None:
            return parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed

    @staticmethod
    def _text(value) -> str:
        return clean_display_text(value or "UNKNOWN").strip().upper()
