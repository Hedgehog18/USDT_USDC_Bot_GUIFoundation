from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from backtest.backtest_engine import BacktestEngine
from backtest.historical_data_provider import HistoricalCandle
from config.config_manager import BotConfig
from market.models import MarketState
from strategy.profile_decision_engine import SMALL_TARGET_MULTIPLIER, StrategyProfileDecisionEngine


HORIZONS = (5, 10, 20, 30)
SUPPORTED_DATASET_MODES = ("profile", "no_micro_trend")


@dataclass(frozen=True)
class MLDatasetExportResult:
    path: Path
    rows_written: int
    candidate_rows: int


class MLDatasetExporter:
    """Build a read-only supervised dataset from historical candles."""

    def __init__(self, config: BotConfig, output_dir: str | Path = "data/ml") -> None:
        self.config = config
        self.output_dir = Path(output_dir)

    def export(
        self,
        *,
        candles: list[HistoricalCandle],
        symbol: str,
        interval: str,
        profile: str,
        dataset_mode: str = "profile",
    ) -> MLDatasetExportResult:
        self._validate_dataset_mode(dataset_mode)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        mode_suffix = "" if dataset_mode == "profile" else f"_{dataset_mode}"
        output_path = self.output_dir / f"{symbol.lower()}_{interval}_{profile}{mode_suffix}.csv"

        rows = self._build_rows(candles=candles, profile=profile, dataset_mode=dataset_mode)
        with output_path.open("w", newline="", encoding="utf-8") as file:
            writer = csv.DictWriter(file, fieldnames=self._fieldnames())
            writer.writeheader()
            writer.writerows(rows)

        candidate_rows = sum(1 for row in rows if row["candidate_direction"] in {"BUY_USDC", "SELL_USDC"})
        return MLDatasetExportResult(
            path=output_path,
            rows_written=len(rows),
            candidate_rows=candidate_rows,
        )

    def _build_rows(self, *, candles: list[HistoricalCandle], profile: str, dataset_mode: str) -> list[dict]:
        if len(candles) < 31:
            return []

        state_builder = BacktestEngine(self.config)
        decision_engine = StrategyProfileDecisionEngine(self.config, profile)
        closes = [candle.close for candle in candles]
        rows = []

        for index in range(30, len(candles)):
            candle = candles[index]
            window = closes[max(0, index - 30):index]
            state = state_builder._build_state(current_price=candle.close, prices=window)
            decision = decision_engine.make_decision(state)
            candidate_direction = self._candidate_direction(
                state=state,
                profile=profile,
                dataset_mode=dataset_mode,
                profile_action=decision.action,
            )
            target_profit = decision.target_profit if dataset_mode == "profile" else self._target_profit(profile)
            target_price = self._target_price(candle.close, candidate_direction, target_profit)
            future = candles[index + 1:]
            horizon_hits = {
                horizon: self._target_hit_within(
                    direction=candidate_direction,
                    target_price=target_price,
                    future_candles=future[:horizon],
                )
                for horizon in HORIZONS
            }
            max_favorable, max_adverse = self._movement_extremes(
                direction=candidate_direction,
                entry_price=candle.close,
                future_candles=future[:max(HORIZONS)],
            )

            rows.append({
                "timestamp": self._timestamp(candle.open_time),
                "dataset_mode": dataset_mode,
                "open": self._format_float(candle.open),
                "high": self._format_float(candle.high),
                "low": self._format_float(candle.low),
                "close": self._format_float(candle.close),
                "work_position": self._format_float(state.work_position),
                "short_position": self._format_float(state.short_position),
                "long_position": self._format_float(state.long_position),
                "micro_trend": state.micro_trend,
                "market_regime": state.market_regime,
                "volatility_regime": state.volatility_regime,
                "spread": self._format_float(state.spread),
                "candidate_direction": candidate_direction,
                "target_price": self._format_float(target_price) if target_price is not None else "",
                "target_hit_5": int(horizon_hits[5]),
                "target_hit_10": int(horizon_hits[10]),
                "target_hit_20": int(horizon_hits[20]),
                "target_hit_30": int(horizon_hits[30]),
                "max_favorable_move": self._format_float(max_favorable) if max_favorable is not None else "",
                "max_adverse_move": self._format_float(max_adverse) if max_adverse is not None else "",
                "label_target_hit": int(horizon_hits[30]),
            })

        return rows

    def _candidate_direction(
        self,
        *,
        state: MarketState,
        profile: str,
        dataset_mode: str,
        profile_action: str,
    ) -> str:
        if dataset_mode == "profile":
            return profile_action if profile_action in {"BUY_USDC", "SELL_USDC"} else "WAIT"

        if not self._safety_filters_pass(state):
            return "WAIT"
        if state.work_position <= self._buy_zone_max(profile):
            return "BUY_USDC"
        if state.work_position >= self._sell_zone_min(profile):
            return "SELL_USDC"
        return "WAIT"

    def _buy_zone_max(self, profile: str) -> float:
        if profile in {"mean_reversion_v2", "mean_reversion_v2_small_target"}:
            return 25.0
        return self.config.buy_zone_max

    def _sell_zone_min(self, profile: str) -> float:
        if profile in {"mean_reversion_v2", "mean_reversion_v2_small_target"}:
            return 75.0
        return self.config.sell_zone_min

    def _target_profit(self, profile: str) -> float:
        if profile == "mean_reversion_v2_small_target":
            return self.config.target_profit * SMALL_TARGET_MULTIPLIER
        return self.config.target_profit

    def _safety_filters_pass(self, state: MarketState) -> bool:
        return (
            0.0 < state.spread <= self.config.max_allowed_spread
            and state.market_health_score >= self.config.min_market_health_score
            and state.market_health_status != "UNHEALTHY"
            and state.market_regime != "ABNORMAL"
            and state.volatility_regime != "EXTREME"
        )

    @staticmethod
    def _target_price(entry_price: float, direction: str, target_profit: float) -> float | None:
        if direction == "BUY_USDC":
            return entry_price * (1.0 + target_profit)
        if direction == "SELL_USDC":
            return entry_price * (1.0 - target_profit)
        return None

    @staticmethod
    def _target_hit_within(
        *,
        direction: str,
        target_price: float | None,
        future_candles: list[HistoricalCandle],
    ) -> bool:
        if target_price is None:
            return False
        if direction == "BUY_USDC":
            return any(candle.high >= target_price for candle in future_candles)
        if direction == "SELL_USDC":
            return any(candle.low <= target_price for candle in future_candles)
        return False

    @staticmethod
    def _movement_extremes(
        *,
        direction: str,
        entry_price: float,
        future_candles: list[HistoricalCandle],
    ) -> tuple[float | None, float | None]:
        if direction not in {"BUY_USDC", "SELL_USDC"} or not future_candles:
            return None, None
        movements = []
        for candle in future_candles:
            if direction == "BUY_USDC":
                movements.extend([candle.high - entry_price, candle.low - entry_price])
            else:
                movements.extend([entry_price - candle.low, entry_price - candle.high])
        return max(movements), min(movements)

    @staticmethod
    def _timestamp(open_time: int) -> str:
        return datetime.fromtimestamp(open_time / 1000, tz=timezone.utc).isoformat()

    @staticmethod
    def _format_float(value: float) -> str:
        return f"{value:.10f}"

    @staticmethod
    def _fieldnames() -> list[str]:
        return [
            "timestamp",
            "dataset_mode",
            "open",
            "high",
            "low",
            "close",
            "work_position",
            "short_position",
            "long_position",
            "micro_trend",
            "market_regime",
            "volatility_regime",
            "spread",
            "candidate_direction",
            "target_price",
            "target_hit_5",
            "target_hit_10",
            "target_hit_20",
            "target_hit_30",
            "max_favorable_move",
            "max_adverse_move",
            "label_target_hit",
        ]

    @staticmethod
    def _validate_dataset_mode(dataset_mode: str) -> None:
        if dataset_mode not in SUPPORTED_DATASET_MODES:
            supported = ", ".join(SUPPORTED_DATASET_MODES)
            raise ValueError(f"Unsupported dataset mode: {dataset_mode}. Supported: {supported}")
