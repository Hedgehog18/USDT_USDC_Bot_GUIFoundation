from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import mean
from typing import Any

from strategy.profile_decision_engine import HF_MICRO_TARGET_PROFIT
from storage.database_manager import DatabaseManager


@dataclass(frozen=True)
class HFRealCycleExecutionDiagnostics:
    db_id: int
    campaign_id: str
    direction: str
    open_price: float
    close_price: float | None
    target_price: float
    quantity: float
    opened_at: str
    closed_at: str | None
    holding_seconds: float | None
    close_reason: str | None
    net_profit: float
    price_after_5s: float | None
    price_after_15s: float | None
    price_after_30s: float | None
    price_after_60s: float | None
    price_after_120s: float | None
    price_after_270s: float | None
    max_favorable_excursion: float | None
    max_adverse_excursion: float | None
    target_touched: bool
    reference_target_touched: bool
    executable_target_touched: bool
    real_target_close_triggered: bool
    target_close_order_sent: bool
    target_close_order_filled: bool
    nearest_target_seconds: float | None
    missed_target_distance: float | None
    paper_would_open: bool
    paper_target_hit: bool
    paper_timeout: bool
    paper_equivalent_net: float
    real_minus_paper_delta: float
    entry_slippage: float | None
    close_slippage: float | None
    spread_at_entry: float | None
    spread_at_close: float | None
    execution_delay_seconds: float | None
    filled_quantity: float | None
    quote_amount: float | None
    commission: float | None
    maker_taker_role: str


@dataclass(frozen=True)
class HFRealVsPaperDiagnosticsReport:
    profile: str
    cycles: list[HFRealCycleExecutionDiagnostics]
    total_real_cycles: int
    target_closes: int
    timeout_closes: int
    timeout_loss_count: int
    real_net: float
    estimated_paper_equivalent_net: float
    real_minus_paper_delta: float
    main_suspected_issue: str
    recommendation: str


class HFRealVsPaperDiagnosticsEngine:
    OFFSETS_SECONDS = (5, 15, 30, 60, 120, 270)

    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def build_report(self, profile: str = "mean_reversion_hf_micro_v1") -> HFRealVsPaperDiagnosticsReport:
        cycles = [self._build_cycle(row, profile) for row in self._load_real_cycles(profile)]
        target_closes = sum(1 for item in cycles if item.close_reason == "real_pilot_target")
        timeout_closes = sum(1 for item in cycles if self._is_timeout_reason(item.close_reason))
        timeout_loss_count = sum(1 for item in cycles if self._is_timeout_reason(item.close_reason) and item.net_profit < 0)
        real_net = sum(item.net_profit for item in cycles)
        paper_net = sum(item.paper_equivalent_net for item in cycles)
        delta = real_net - paper_net
        issue = self._suspected_issue(cycles, timeout_closes, timeout_loss_count, delta)
        return HFRealVsPaperDiagnosticsReport(
            profile=profile,
            cycles=cycles,
            total_real_cycles=len(cycles),
            target_closes=target_closes,
            timeout_closes=timeout_closes,
            timeout_loss_count=timeout_loss_count,
            real_net=real_net,
            estimated_paper_equivalent_net=paper_net,
            real_minus_paper_delta=delta,
            main_suspected_issue=issue,
            recommendation=self._recommendation(issue, len(cycles), real_net),
        )

    def _build_cycle(self, row: dict[str, Any], profile: str) -> HFRealCycleExecutionDiagnostics:
        target_price = self._target_price(row["direction"], row["open_price"])
        opened_at = self._parse_time(row["opened_at"])
        closed_at = self._parse_time(row["closed_at"]) if row["closed_at"] else None
        snapshots = self._load_market_path(row, row["opened_at"], row["closed_at"] or row["opened_at"])
        entry_snapshot = self._nearest_snapshot(snapshots, opened_at) if opened_at else None
        close_snapshot = self._nearest_snapshot(snapshots, closed_at) if closed_at else None
        prices = [snapshot["price"] for snapshot in snapshots]
        offsets = {
            offset: self._price_at_offset(snapshots, opened_at, offset)
            for offset in self.OFFSETS_SECONDS
        }
        mfe = self._max_favorable(row["direction"], row["open_price"], prices)
        mae = self._max_adverse(row["direction"], row["open_price"], prices)
        reference_target_touched = any(self._target_hit(row["direction"], price, target_price) for price in prices)
        executable_target_touched = any(
            self._target_hit(row["direction"], reference, target_price)
            for reference in (
                self._executable_reference(row["direction"], snapshot, role="close")
                for snapshot in snapshots
            )
            if reference is not None
        )
        close_order_sent, close_order_filled = self._target_close_order_state(row)
        nearest_seconds, missed_distance = self._nearest_target_distance(snapshots, opened_at, row["direction"], target_price)
        paper_would_open = self._paper_would_open(row["direction"], entry_snapshot)
        paper_target_hit = reference_target_touched
        paper_timeout = (not paper_target_hit) and self._is_timeout_reason(row["close_reason"])
        paper_net = self._paper_equivalent_net(row, snapshots, target_price)
        entry_exec = self._execution_for_cycle(row, role="entry")
        close_exec = self._execution_for_cycle(row, role="close")
        entry_ref = self._executable_reference(row["direction"], entry_snapshot, role="entry")
        close_ref = self._executable_reference(row["direction"], close_snapshot, role="close")
        return HFRealCycleExecutionDiagnostics(
            db_id=row["id"],
            campaign_id=row["campaign_id"],
            direction=row["direction"],
            open_price=row["open_price"],
            close_price=row["close_price"],
            target_price=target_price,
            quantity=row["quantity"],
            opened_at=row["opened_at"],
            closed_at=row["closed_at"],
            holding_seconds=self._holding_seconds(opened_at, closed_at),
            close_reason=row["close_reason"],
            net_profit=row["net_profit"],
            price_after_5s=offsets[5],
            price_after_15s=offsets[15],
            price_after_30s=offsets[30],
            price_after_60s=offsets[60],
            price_after_120s=offsets[120],
            price_after_270s=offsets[270],
            max_favorable_excursion=mfe,
            max_adverse_excursion=mae,
            target_touched=reference_target_touched,
            reference_target_touched=reference_target_touched,
            executable_target_touched=executable_target_touched,
            real_target_close_triggered=row["close_reason"] == "real_pilot_target",
            target_close_order_sent=close_order_sent,
            target_close_order_filled=close_order_filled,
            nearest_target_seconds=nearest_seconds,
            missed_target_distance=missed_distance,
            paper_would_open=paper_would_open,
            paper_target_hit=paper_target_hit,
            paper_timeout=paper_timeout,
            paper_equivalent_net=paper_net,
            real_minus_paper_delta=row["net_profit"] - paper_net,
            entry_slippage=(row["open_price"] - entry_ref) if entry_ref is not None else None,
            close_slippage=(row["close_price"] - close_ref) if row["close_price"] is not None and close_ref is not None else None,
            spread_at_entry=entry_snapshot.get("spread") if entry_snapshot else None,
            spread_at_close=close_snapshot.get("spread") if close_snapshot else None,
            execution_delay_seconds=self._execution_delay(opened_at, entry_exec),
            filled_quantity=entry_exec.get("executed_qty"),
            quote_amount=entry_exec.get("quote_amount"),
            commission=(entry_exec.get("commission") or 0.0) + (close_exec.get("commission") or 0.0),
            maker_taker_role=entry_exec.get("role") or close_exec.get("role") or "N/A",
        )

    def _load_real_cycles(self, profile: str) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT
                    c.id, c.timestamp, c.strategy_profile, c.symbol, c.direction,
                    c.status, c.open_price, c.close_price, c.quantity, c.stake_usdt,
                    c.net_profit, c.opened_at, c.closed_at, c.close_reason,
                    c.exchange_order_id, c.run_id,
                    COALESCE((
                        SELECT campaign_id
                        FROM real_pilot_campaigns
                        WHERE strategy_profile = c.strategy_profile
                          AND c.id > baseline_cycle_id
                          AND c.opened_at >= started_at
                          AND (finished_at IS NULL OR c.opened_at <= finished_at)
                        ORDER BY started_at DESC
                        LIMIT 1
                    ), c.run_id) AS campaign_id
                FROM real_pilot_cycles c
                WHERE c.strategy_profile = ?
                  AND c.status IN ('CLOSED', 'HALTED')
                ORDER BY c.id ASC
                """,
                (profile,),
            ).fetchall()
        keys = [
            "id", "timestamp", "strategy_profile", "symbol", "direction", "status",
            "open_price", "close_price", "quantity", "stake_usdt", "net_profit",
            "opened_at", "closed_at", "close_reason", "exchange_order_id", "run_id",
            "campaign_id",
        ]
        return [dict(zip(keys, row)) for row in rows]

    def _load_market_path(self, cycle: dict[str, Any], start: str, end: str) -> list[dict[str, Any]]:
        blackbox = self._load_blackbox_snapshots(int(cycle["id"]))
        if blackbox:
            return blackbox
        return self._load_hf_snapshots(start, end)

    def _load_blackbox_snapshots(self, real_cycle_id: int) -> list[dict[str, Any]]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT timestamp, price, bid, ask, mid, spread,
                       short_center, candidate, block_reason
                FROM real_pilot_market_snapshots
                WHERE real_cycle_id = ?
                  AND price IS NOT NULL
                  AND phase IN ('entry', 'tracking', 'exit', 'post_exit')
                ORDER BY timestamp ASC, id ASC
                """,
                (real_cycle_id,),
            ).fetchall()
        keys = [
            "timestamp", "price", "bid", "ask", "mid_price", "spread",
            "short_center", "would_open_cycle", "reason_if_not",
        ]
        return [dict(zip(keys, row)) for row in rows]

    def _load_hf_snapshots(self, start: str, end: str) -> list[dict[str, Any]]:
        start_dt = self._parse_time(start)
        end_dt = self._parse_time(end) or start_dt
        if start_dt is None:
            return []
        # Include a small buffer so nearest snapshots around entry/close can be used.
        lower = (start_dt - timedelta(seconds=5)).isoformat()
        upper = ((end_dt or start_dt) + timedelta(seconds=300)).isoformat()
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT timestamp, price, bid, ask, mid_price, spread,
                       distance_to_short_center, would_open_cycle, reason_if_not
                FROM market_snapshots_hf
                WHERE timestamp >= ? AND timestamp <= ?
                ORDER BY timestamp ASC
                """,
                (lower, upper),
            ).fetchall()
        keys = [
            "timestamp", "price", "bid", "ask", "mid_price", "spread",
            "distance_to_short_center", "would_open_cycle", "reason_if_not",
        ]
        return [dict(zip(keys, row)) for row in rows]

    def _execution_for_cycle(self, cycle: dict[str, Any], *, role: str) -> dict[str, float | str | None]:
        with self.database.connect() as conn:
            if role == "entry":
                rows = conn.execute(
                    """
                    SELECT timestamp, side, quantity, status, request_payload, response_payload
                    FROM real_pilot_order_events
                    WHERE strategy_profile = ?
                      AND run_id = ?
                      AND status = 'FILLED'
                    ORDER BY id ASC
                    """,
                    (cycle["strategy_profile"], cycle["run_id"]),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT timestamp, side, quantity, status, request_payload, response_payload
                    FROM real_pilot_order_events
                    WHERE strategy_profile = ?
                      AND status = 'FILLED'
                    ORDER BY id ASC
                    """,
                    (cycle["strategy_profile"],),
                ).fetchall()
        for row in rows:
            request = self._json(row[4])
            if role == "close" and int(request.get("close_cycle_id", -1)) != int(cycle["id"]):
                continue
            return self._parse_execution(row[0], row[1], row[5])
        return {"timestamp": None, "executed_qty": None, "quote_amount": None, "commission": None, "role": "N/A"}

    def _target_close_order_state(self, cycle: dict[str, Any]) -> tuple[bool, bool]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT status, request_payload
                FROM real_pilot_order_events
                WHERE strategy_profile = ?
                ORDER BY id ASC
                """,
                (cycle["strategy_profile"],),
            ).fetchall()
        sent = False
        filled = False
        for row in rows:
            request = self._json(row[1])
            if int(request.get("close_cycle_id", -1)) != int(cycle["id"]):
                continue
            if request.get("close_reason") != "real_pilot_target":
                continue
            sent = True
            if str(row[0]) == "FILLED":
                filled = True
        return sent, filled

    def _parse_execution(self, timestamp: str, side: str, payload: str) -> dict[str, float | str | None]:
        data = self._json(payload)
        fills = data.get("fills") or []
        executed_qty = self._float(data.get("executedQty"))
        quote_amount = self._float(data.get("cummulativeQuoteQty"))
        commission = 0.0
        role = "TAKER" if fills else "N/A"
        if fills:
            commission = sum(self._float(fill.get("commission")) or 0.0 for fill in fills)
            if quote_amount is None:
                quote_amount = sum((self._float(fill.get("price")) or 0.0) * (self._float(fill.get("qty")) or 0.0) for fill in fills)
        return {
            "timestamp": timestamp,
            "side": side,
            "executed_qty": executed_qty,
            "quote_amount": quote_amount,
            "commission": commission,
            "role": role,
        }

    @staticmethod
    def _json(value: str) -> dict[str, Any]:
        try:
            parsed = json.loads(value or "{}")
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}

    @staticmethod
    def _target_price(direction: str, open_price: float) -> float:
        if direction == "BUY_USDC":
            return open_price * (1.0 + HF_MICRO_TARGET_PROFIT)
        return open_price * (1.0 - HF_MICRO_TARGET_PROFIT)

    @staticmethod
    def _target_hit(direction: str, price: float, target_price: float) -> bool:
        if direction == "BUY_USDC":
            return price >= target_price
        return price <= target_price

    @staticmethod
    def _is_timeout_reason(reason: str | None) -> bool:
        text = str(reason or "")
        return "holding" in text or "timeout" in text

    @staticmethod
    def _parse_time(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(str(value))
        except ValueError:
            return None

    @staticmethod
    def _holding_seconds(opened: datetime | None, closed: datetime | None) -> float | None:
        if opened is None or closed is None:
            return None
        return max(0.0, (closed - opened).total_seconds())

    def _price_at_offset(self, snapshots: list[dict[str, Any]], opened_at: datetime | None, offset: int) -> float | None:
        if opened_at is None:
            return None
        return self._nearest_snapshot_price(snapshots, opened_at + timedelta(seconds=offset))

    def _nearest_snapshot_price(self, snapshots: list[dict[str, Any]], target_time: datetime) -> float | None:
        snapshot = self._nearest_snapshot(snapshots, target_time)
        return snapshot.get("price") if snapshot else None

    def _nearest_snapshot(self, snapshots: list[dict[str, Any]], target_time: datetime | None) -> dict[str, Any] | None:
        if target_time is None or not snapshots:
            return None
        return min(
            snapshots,
            key=lambda row: abs(((self._parse_time(row["timestamp"]) or target_time) - target_time).total_seconds()),
        )

    @staticmethod
    def _max_favorable(direction: str, open_price: float, prices: list[float]) -> float | None:
        if not prices:
            return None
        if direction == "BUY_USDC":
            return max(price - open_price for price in prices)
        return max(open_price - price for price in prices)

    @staticmethod
    def _max_adverse(direction: str, open_price: float, prices: list[float]) -> float | None:
        if not prices:
            return None
        if direction == "BUY_USDC":
            return min(price - open_price for price in prices)
        return min(open_price - price for price in prices)

    def _nearest_target_distance(
        self,
        snapshots: list[dict[str, Any]],
        opened_at: datetime | None,
        direction: str,
        target_price: float,
    ) -> tuple[float | None, float | None]:
        if opened_at is None or not snapshots:
            return None, None
        best = min(snapshots, key=lambda row: abs(float(row["price"]) - target_price))
        best_time = self._parse_time(best["timestamp"])
        seconds = abs((best_time - opened_at).total_seconds()) if best_time else None
        distance = abs(float(best["price"]) - target_price)
        return seconds, distance

    @staticmethod
    def _paper_would_open(direction: str, snapshot: dict[str, Any] | None) -> bool:
        if not snapshot:
            return False
        price = float(snapshot["price"])
        if snapshot.get("short_center") is not None:
            short_center = float(snapshot["short_center"])
        else:
            short_center = price - float(snapshot.get("distance_to_short_center") or 0.0)
        if direction == "BUY_USDC":
            return price < short_center
        return price > short_center

    def _paper_equivalent_net(self, cycle: dict[str, Any], snapshots: list[dict[str, Any]], target_price: float) -> float:
        quantity = float(cycle["quantity"])
        open_price = float(cycle["open_price"])
        direction = str(cycle["direction"])
        for snapshot in snapshots:
            price = float(snapshot["price"])
            if self._target_hit(direction, price, target_price):
                return self._pnl(direction, open_price, target_price, quantity)
        close_price = float(cycle["close_price"] or open_price)
        if snapshots:
            close_price = float(snapshots[-1]["price"])
        return self._pnl(direction, open_price, close_price, quantity)

    @staticmethod
    def _pnl(direction: str, open_price: float, close_price: float, quantity: float) -> float:
        if direction == "BUY_USDC":
            return (close_price - open_price) * quantity
        return (open_price - close_price) * quantity

    @staticmethod
    def _executable_reference(direction: str, snapshot: dict[str, Any] | None, *, role: str) -> float | None:
        if not snapshot:
            return None
        if role == "entry":
            return float(snapshot["ask"] if direction == "BUY_USDC" else snapshot["bid"])
        return float(snapshot["bid"] if direction == "BUY_USDC" else snapshot["ask"])

    def _execution_delay(self, opened_at: datetime | None, execution: dict[str, Any]) -> float | None:
        execution_time = self._parse_time(str(execution.get("timestamp") or ""))
        if opened_at is None or execution_time is None:
            return None
        return max(0.0, (execution_time - opened_at).total_seconds())

    @staticmethod
    def _float(value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _suspected_issue(
        cycles: list[HFRealCycleExecutionDiagnostics],
        timeout_closes: int,
        timeout_loss_count: int,
        delta: float,
    ) -> str:
        if not cycles:
            return "unknown"
        if all(item.max_favorable_excursion is None and item.max_adverse_excursion is None for item in cycles):
            return "data_insufficient"
        avg_spread = mean([item.spread_at_entry for item in cycles if item.spread_at_entry is not None] or [0.0])
        avg_target_distance = mean([abs(item.target_price - item.open_price) for item in cycles] or [0.0])
        if avg_spread >= avg_target_distance and timeout_loss_count > 0:
            return "target_too_tight_for_real_spread"
        if delta < 0 and abs(delta) > 0.00001:
            return "execution_spread_issue"
        if timeout_closes >= max(1, len(cycles) // 2):
            return "timeout_policy_issue"
        if all(not item.target_touched for item in cycles):
            return "insufficient_price_movement"
        if any(not item.paper_would_open for item in cycles):
            return "strategy_signal_issue"
        return "unknown"

    @staticmethod
    def _recommendation(issue: str, total_cycles: int, real_net: float) -> str:
        if total_cycles < 10:
            return "RUN_NEW_CAMPAIGN_WITH_RECORDER" if issue == "data_insufficient" else "COMPARE_WITH_LIVE_PAPER"
        if issue == "data_insufficient":
            return "ENABLE_BLACK_BOX_RECORDER"
        if issue in {"target_too_tight_for_real_spread", "execution_spread_issue"}:
            return "TUNE_REAL_TARGET_OR_SPREAD"
        if real_net < 0:
            return "KEEP_REAL_PAUSED"
        if issue == "unknown":
            return "RUN_MORE_SMALL_REAL"
        return "COMPARE_WITH_LIVE_PAPER"
