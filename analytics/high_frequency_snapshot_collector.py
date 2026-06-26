from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime, timedelta

from config.config_manager import BotConfig
from market.market_analyzer import MarketAnalyzer
from market.models import MarketState
from storage.database_manager import DatabaseManager


PRICE_CHANGE_WINDOWS = (
    ("price_change_5_sec", 5),
    ("price_change_10_sec", 10),
    ("price_change_30_sec", 30),
    ("price_change_1_min", 60),
    ("price_change_5_min", 300),
)


@dataclass(frozen=True)
class HighFrequencyCollectionResult:
    snapshots_collected: int
    duration_seconds: float
    interval_seconds: float


class HighFrequencySnapshotCollector:
    def __init__(
        self,
        database: DatabaseManager,
        config: BotConfig,
        analyzer: MarketAnalyzer | None = None,
    ) -> None:
        self.database = database
        self.config = config
        self.analyzer = analyzer or MarketAnalyzer(
            symbol=config.symbol,
            use_real_data=config.use_real_market_data,
            config=config,
        )
        self.history = self._load_history()

    def collect(
        self,
        *,
        duration_hours: float,
        interval_seconds: float,
        max_snapshots: int | None = None,
    ) -> HighFrequencyCollectionResult:
        if duration_hours < 0:
            raise ValueError("--duration-hours must be 0 or greater.")
        if interval_seconds <= 0:
            raise ValueError("--interval must be greater than 0.")
        if max_snapshots is not None and max_snapshots <= 0:
            raise ValueError("--max-snapshots must be greater than 0 when provided.")

        started = time.monotonic()
        deadline = started + duration_hours * 3600.0
        collected = 0

        while time.monotonic() <= deadline:
            market_state = self.analyzer.analyze_market()
            snapshot = self.build_snapshot(
                market_state,
                data_source=getattr(self.analyzer, "last_data_source", "UNKNOWN"),
            )
            self.database.save_hf_market_snapshot(snapshot)
            self.history.append((self._parse_timestamp(snapshot["timestamp"]), snapshot["price"]))
            collected += 1

            if max_snapshots is not None and collected >= max_snapshots:
                break
            if time.monotonic() + interval_seconds > deadline:
                break
            time.sleep(interval_seconds)

        return HighFrequencyCollectionResult(
            snapshots_collected=collected,
            duration_seconds=time.monotonic() - started,
            interval_seconds=interval_seconds,
        )

    def build_snapshot(self, market_state: MarketState, data_source: str = "UNKNOWN") -> dict:
        timestamp = market_state.created_at.isoformat()
        entry_zone = self._entry_zone(market_state.work_position)
        buy_zone = entry_zone == "BUY"
        sell_zone = entry_zone == "SELL"
        would_open_cycle, reason_if_not = self._entry_decision(market_state, entry_zone)
        price_changes = self._price_changes(market_state.created_at, market_state.price)

        return {
            "timestamp": timestamp,
            "symbol": market_state.symbol,
            "price": market_state.price,
            "bid": market_state.bid,
            "ask": market_state.ask,
            "mid_price": (market_state.bid + market_state.ask) / 2.0,
            "spread": market_state.spread,
            "work_position": market_state.work_position,
            "micro_trend": market_state.micro_trend,
            "entry_zone": entry_zone,
            "buy_zone": buy_zone,
            "sell_zone": sell_zone,
            "volatility_regime": market_state.volatility_regime,
            "market_regime": market_state.market_regime,
            "distance_to_long_center": market_state.price - market_state.long_center,
            "distance_to_short_center": market_state.price - market_state.short_center,
            "distance_to_work_center": market_state.price - market_state.work_center,
            "order_book_pressure": market_state.order_book_pressure,
            "session": self.classify_session(market_state.created_at.hour),
            "price_change_5_sec": price_changes["price_change_5_sec"],
            "price_change_10_sec": price_changes["price_change_10_sec"],
            "price_change_30_sec": price_changes["price_change_30_sec"],
            "price_change_1_min": price_changes["price_change_1_min"],
            "price_change_5_min": price_changes["price_change_5_min"],
            "would_open_cycle": would_open_cycle,
            "reason_if_not": reason_if_not,
            "data_source": data_source,
        }

    def _entry_decision(self, market_state: MarketState, entry_zone: str) -> tuple[bool, str]:
        if not (0.0 < market_state.spread <= self.config.max_allowed_spread):
            return False, "spread"
        if (
            market_state.market_health_score < self.config.min_market_health_score
            or market_state.market_health_status == "UNHEALTHY"
        ):
            return False, "safety"
        if market_state.market_regime == "ABNORMAL":
            return False, "market_regime"
        if market_state.volatility_regime == "EXTREME":
            return False, "volatility_regime"
        if entry_zone == "CENTER":
            return False, "entry_zone"
        if entry_zone == "BUY" and market_state.micro_trend != "BUY_DOMINANT":
            return False, "micro_trend"
        if entry_zone == "SELL" and market_state.micro_trend != "SELL_DOMINANT":
            return False, "micro_trend"
        return True, ""

    @staticmethod
    def _entry_zone(work_position: float) -> str:
        if work_position <= 25.0:
            return "BUY"
        if work_position >= 75.0:
            return "SELL"
        return "CENTER"

    def _price_changes(self, timestamp: datetime, price: float) -> dict[str, float]:
        return {
            key: price - self._reference_price(timestamp - timedelta(seconds=seconds), price)
            for key, seconds in PRICE_CHANGE_WINDOWS
        }

    def _reference_price(self, cutoff: datetime, current_price: float) -> float:
        candidates = [
            (timestamp, price)
            for timestamp, price in self.history
            if timestamp is not None and timestamp <= cutoff
        ]
        if not candidates:
            return current_price
        return max(candidates, key=lambda item: item[0])[1]

    def _load_history(self) -> list[tuple[datetime | None, float]]:
        rows = self.database.load_recent_hf_market_snapshots(limit=5000)
        return [
            (self._parse_timestamp(timestamp), float(price or 0.0))
            for timestamp, price in reversed(rows)
        ]

    @staticmethod
    def classify_session(hour: int) -> str:
        if 13 <= hour <= 16:
            return "LONDON_NEW_YORK_OVERLAP"
        if 8 <= hour <= 12:
            return "LONDON"
        if 17 <= hour <= 23:
            return "NEW_YORK"
        return "ASIA"

    @staticmethod
    def _parse_timestamp(value: str) -> datetime | None:
        try:
            return datetime.fromisoformat(value)
        except (TypeError, ValueError):
            return None
