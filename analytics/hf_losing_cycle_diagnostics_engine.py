from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from statistics import median

from app.text_encoding import clean_display_text
from storage.database_manager import DatabaseManager
from strategy.profile_decision_engine import HF_MICRO_TARGET_PROFIT


ONE_TICK = 0.00001


@dataclass(frozen=True)
class HFLosingCycleDetail:
    db_id: int
    direction: str
    open_price: float
    close_price: float
    target_price: float
    close_reason: str
    holding_time_seconds: float | None
    net_profit: float
    immediate_adverse_move: str
    against_short_center_movement: str
    flat_before_entry: str
    last_different_fallback_used: str
    short_center_at_entry: str
    current_price_at_entry: str
    previous_price: str
    last_different_price: str
    hf_entry_mode: str
    price_buffer_unique_values: str
    flat_samples_count: str
    flat_price_buffer: str
    max_favorable_move: str
    max_adverse_move: str
    did_price_ever_touch_target_before_timeout: str
    minimum_distance_to_target: str
    near_target_samples: str
    price_at_timeout_close: str
    category: str


@dataclass(frozen=True)
class HFLossCategorySummary:
    category: str
    count: int
    net_loss: float
    average_loss: float


@dataclass(frozen=True)
class HFLosingCycleDiagnosticsReport:
    profile: str
    since_id: int
    limit: int | None
    total_cycles: int
    losing_cycles_count: int
    losing_cycles_rate: float
    total_loss_net: float
    average_loss: float
    median_loss: float
    worst_loss: float
    buy_losses_count: int
    buy_losses_net: float
    sell_losses_count: int
    sell_losses_net: float
    timeout_losses_count: int
    timeout_losses_net: float
    target_losses_count: int
    target_losses_net: float
    details: list[HFLosingCycleDetail]
    categories: list[HFLossCategorySummary]
    recommendations: list[str]


class HFLosingCycleDiagnosticsEngine:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def build_report(
        self,
        *,
        profile: str,
        since_id: int = 0,
        limit: int | None = None,
    ) -> HFLosingCycleDiagnosticsReport:
        total_cycles = self._count_realized_cycles(profile=profile, since_id=since_id)
        rows = self._load_losing_cycles(profile=profile, since_id=since_id, limit=limit)
        details = [self._build_detail(row) for row in rows]
        net_values = [detail.net_profit for detail in details]
        buy_losses = [detail for detail in details if detail.direction == "BUY_USDC"]
        sell_losses = [detail for detail in details if detail.direction == "SELL_USDC"]
        timeout_losses = [
            detail for detail in details if detail.close_reason.startswith("max_holding_")
        ]
        target_losses = [detail for detail in details if detail.close_reason == "target"]
        categories = self._category_summaries(details)

        return HFLosingCycleDiagnosticsReport(
            profile=profile,
            since_id=since_id,
            limit=limit,
            total_cycles=total_cycles,
            losing_cycles_count=len(details),
            losing_cycles_rate=(len(details) / total_cycles) if total_cycles else 0.0,
            total_loss_net=sum(net_values),
            average_loss=(sum(net_values) / len(net_values)) if net_values else 0.0,
            median_loss=median(net_values) if net_values else 0.0,
            worst_loss=min(net_values) if net_values else 0.0,
            buy_losses_count=len(buy_losses),
            buy_losses_net=sum(detail.net_profit for detail in buy_losses),
            sell_losses_count=len(sell_losses),
            sell_losses_net=sum(detail.net_profit for detail in sell_losses),
            timeout_losses_count=len(timeout_losses),
            timeout_losses_net=sum(detail.net_profit for detail in timeout_losses),
            target_losses_count=len(target_losses),
            target_losses_net=sum(detail.net_profit for detail in target_losses),
            details=details,
            categories=categories,
            recommendations=self._recommendations(categories, details),
        )

    def _count_realized_cycles(self, *, profile: str, since_id: int) -> int:
        with self.database.connect() as conn:
            row = conn.execute(
                """
                SELECT COUNT(*)
                FROM paper_cycles
                WHERE strategy_profile = ?
                  AND id > ?
                  AND status IN ('CLOSED', 'CLOSED_MANUAL')
                """,
                (profile, since_id),
            ).fetchone()
        return int(row[0])

    def _load_losing_cycles(self, *, profile: str, since_id: int, limit: int | None) -> list[dict]:
        limit_clause = "" if limit is None else "LIMIT ?"
        params: list[object] = [profile, since_id]
        if limit is not None:
            params.append(limit)
        with self.database.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT
                    c.id, c.direction, c.open_price, c.close_price, c.net_profit,
                    c.opened_at, c.closed_at, c.close_reason,
                    d.current_price, d.short_center, d.previous_price,
                    d.last_different_price, d.hf_entry_mode,
                    d.price_buffer_unique_values, d.flat_samples_count,
                    d.flat_price_buffer, d.entry_reason
                FROM paper_cycles c
                LEFT JOIN hf_paper_cycle_entry_diagnostics d
                    ON d.paper_cycle_id = c.id
                WHERE c.strategy_profile = ?
                  AND c.id > ?
                  AND c.status IN ('CLOSED', 'CLOSED_MANUAL')
                  AND c.net_profit < 0
                ORDER BY c.id DESC
                {limit_clause}
                """,
                tuple(params),
            ).fetchall()

        keys = (
            "db_id",
            "direction",
            "open_price",
            "close_price",
            "net_profit",
            "opened_at",
            "closed_at",
            "close_reason",
            "entry_price",
            "short_center",
            "previous_price",
            "last_different_price",
            "hf_entry_mode",
            "price_buffer_unique_values",
            "flat_samples_count",
            "flat_price_buffer",
            "entry_reason",
        )
        return [dict(zip(keys, row)) for row in rows]

    def _build_detail(self, row: dict) -> HFLosingCycleDetail:
        direction = clean_display_text(row["direction"])
        open_price = float(row["open_price"])
        close_price = float(row["close_price"])
        target_price = self._target_price(direction, open_price)
        close_reason = clean_display_text(row["close_reason"] or "N/A")
        holding_time = self._holding_time(row["opened_at"], row["closed_at"])
        movement = self._post_entry_movement(
            direction=direction,
            open_price=open_price,
            close_price=close_price,
            target_price=target_price,
            opened_at=row["opened_at"],
            closed_at=row["closed_at"],
        )
        immediate_adverse = self._immediate_adverse(direction, open_price, movement["first_price"])
        against_short_center = self._against_short_center_movement(direction, row)
        flat_before_entry = self._flat_before_entry(row)
        fallback_used = "yes" if "equal_center_last_different_fallback" in clean_display_text(row["entry_reason"] or "") else "no"
        category = self._category(
            row=row,
            movement=movement,
            immediate_adverse=immediate_adverse,
            flat_before_entry=flat_before_entry,
            fallback_used=fallback_used,
        )

        return HFLosingCycleDetail(
            db_id=int(row["db_id"]),
            direction=direction,
            open_price=open_price,
            close_price=close_price,
            target_price=target_price,
            close_reason=close_reason,
            holding_time_seconds=holding_time,
            net_profit=float(row["net_profit"]),
            immediate_adverse_move=immediate_adverse,
            against_short_center_movement=against_short_center,
            flat_before_entry=flat_before_entry,
            last_different_fallback_used=fallback_used,
            short_center_at_entry=self._format_optional(row["short_center"]),
            current_price_at_entry=self._format_optional(row["entry_price"]),
            previous_price=self._format_optional(row["previous_price"]),
            last_different_price=self._format_optional(row["last_different_price"]),
            hf_entry_mode=clean_display_text(row["hf_entry_mode"] or "N/A"),
            price_buffer_unique_values=self._format_optional_int(row["price_buffer_unique_values"]),
            flat_samples_count=self._format_optional_int(row["flat_samples_count"]),
            flat_price_buffer=self._format_bool(row["flat_price_buffer"]),
            max_favorable_move=self._format_optional(movement["max_favorable"]),
            max_adverse_move=self._format_optional(movement["max_adverse"]),
            did_price_ever_touch_target_before_timeout=movement["target_touched"],
            minimum_distance_to_target=self._format_optional(movement["min_distance_to_target"]),
            near_target_samples=str(movement["near_target_samples"]) if movement["has_prices"] else "N/A",
            price_at_timeout_close=(
                self._format_optional(close_price) if close_reason.startswith("max_holding_") else "N/A"
            ),
            category=category,
        )

    def _post_entry_movement(
        self,
        *,
        direction: str,
        open_price: float,
        close_price: float,
        target_price: float,
        opened_at: str,
        closed_at: str | None,
    ) -> dict:
        history_prices = self._load_prices_between(opened_at, closed_at)
        prices = [*history_prices, close_price]
        if not prices:
            return {
                "has_prices": False,
                "first_price": None,
                "max_favorable": None,
                "max_adverse": None,
                "target_touched": "N/A",
                "min_distance_to_target": None,
                "near_target_samples": 0,
            }

        if direction == "BUY_USDC":
            favorable = [price - open_price for price in prices]
            adverse = [min(0.0, price - open_price) for price in prices]
            target_touched = any(price >= target_price for price in prices)
        else:
            favorable = [open_price - price for price in prices]
            adverse = [min(0.0, open_price - price) for price in prices]
            target_touched = any(price <= target_price for price in prices)

        distances = [abs(price - target_price) for price in prices]
        return {
            "has_prices": True,
            "first_price": history_prices[0] if history_prices else None,
            "max_favorable": max(favorable),
            "max_adverse": min(adverse),
            "target_touched": "yes" if target_touched else "no",
            "min_distance_to_target": min(distances),
            "near_target_samples": sum(1 for distance in distances if distance <= ONE_TICK),
        }

    def _load_prices_between(self, opened_at: str, closed_at: str | None) -> list[float]:
        if not closed_at:
            return []
        try:
            datetime.fromisoformat(opened_at)
            datetime.fromisoformat(closed_at)
        except (TypeError, ValueError):
            return []
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT price
                FROM market_snapshots_hf
                WHERE timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp ASC
                """,
                (opened_at, closed_at),
            ).fetchall()
        return [float(row[0]) for row in rows]

    @staticmethod
    def _target_price(direction: str, open_price: float) -> float:
        if direction == "BUY_USDC":
            return open_price * (1.0 + HF_MICRO_TARGET_PROFIT)
        return open_price * (1.0 - HF_MICRO_TARGET_PROFIT)

    @staticmethod
    def _holding_time(opened_at: str, closed_at: str | None) -> float | None:
        if not closed_at:
            return None
        try:
            return max(
                0.0,
                (datetime.fromisoformat(closed_at) - datetime.fromisoformat(opened_at)).total_seconds(),
            )
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _immediate_adverse(direction: str, open_price: float, first_price: float | None) -> str:
        if first_price is None:
            return "N/A"
        if direction == "BUY_USDC":
            return "yes" if first_price < open_price else "no"
        return "yes" if first_price > open_price else "no"

    @staticmethod
    def _against_short_center_movement(direction: str, row: dict) -> str:
        entry_price = row.get("entry_price")
        last_different = row.get("last_different_price")
        if entry_price is None or last_different is None:
            return "N/A"
        entry_price = float(entry_price)
        last_different = float(last_different)
        if direction == "BUY_USDC":
            return "yes" if entry_price < last_different else "no"
        return "yes" if entry_price > last_different else "no"

    @staticmethod
    def _flat_before_entry(row: dict) -> str:
        unique_values = row.get("price_buffer_unique_values")
        flat_samples = row.get("flat_samples_count")
        flat_buffer = row.get("flat_price_buffer")
        if unique_values is None and flat_samples is None and flat_buffer is None:
            return "N/A"
        if flat_buffer or (unique_values is not None and int(unique_values) <= 1) or (
            flat_samples is not None and int(flat_samples) >= 20
        ):
            return "yes"
        return "no"

    def _category(self, *, row: dict, movement: dict, immediate_adverse: str, flat_before_entry: str, fallback_used: str) -> str:
        close_reason = clean_display_text(row["close_reason"] or "")
        if row.get("short_center") is None and not movement["has_prices"]:
            return "unknown_insufficient_data"
        if flat_before_entry == "yes":
            return "flat_market_entry"
        if movement["target_touched"] == "no" and movement["min_distance_to_target"] is not None:
            if movement["min_distance_to_target"] <= ONE_TICK:
                return "target_missed_by_one_tick"
        if immediate_adverse == "yes":
            return "wrong_direction"
        if close_reason.startswith("max_holding_"):
            if movement["max_favorable"] is not None and movement["max_favorable"] <= 0.0:
                return "no_follow_through"
            return "timeout_too_short"
        if fallback_used == "yes":
            return "wrong_direction"
        return "unknown_insufficient_data"

    @staticmethod
    def _category_summaries(details: list[HFLosingCycleDetail]) -> list[HFLossCategorySummary]:
        categories = sorted({detail.category for detail in details})
        rows: list[HFLossCategorySummary] = []
        for category in categories:
            matching = [detail for detail in details if detail.category == category]
            net_loss = sum(detail.net_profit for detail in matching)
            rows.append(
                HFLossCategorySummary(
                    category=category,
                    count=len(matching),
                    net_loss=net_loss,
                    average_loss=net_loss / len(matching) if matching else 0.0,
                )
            )
        return rows

    @staticmethod
    def _recommendations(categories: list[HFLossCategorySummary], details: list[HFLosingCycleDetail]) -> list[str]:
        if not details:
            return ["no action yet"]
        names = {item.category for item in categories}
        recommendations: list[str] = []
        if "wrong_direction" in names:
            recommendations.append("tune entry direction")
        if "no_follow_through" in names:
            recommendations.append("tune entry direction")
        if "flat_market_entry" in names:
            recommendations.append("tune flat filter")
        if "timeout_too_short" in names:
            recommendations.append("tune max holding")
        if "target_missed_by_one_tick" in names:
            recommendations.append("add near-target tolerance")
        if "unknown_insufficient_data" in names:
            recommendations.append("collect more entry diagnostics")
        if not recommendations:
            recommendations.append("no action yet")
        return recommendations

    @staticmethod
    def _format_optional(value) -> str:
        if value is None:
            return "N/A"
        return f"{float(value):.8f}"

    @staticmethod
    def _format_optional_int(value) -> str:
        if value is None:
            return "N/A"
        return str(int(value))

    @staticmethod
    def _format_bool(value) -> str:
        if value is None:
            return "N/A"
        return "yes" if bool(value) else "no"
