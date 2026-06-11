from dataclasses import dataclass, field

from config.config_manager import BotConfig


ENTRY_ACTIONS = {"BUY_USDC", "SELL_USDC"}


@dataclass
class EntryZoneDebugItem:
    index: int
    timestamp: str
    bid: float
    ask: float
    mid_price: float
    spread: float
    reference_price: float
    deviation_from_mean: float
    deviation_from_mean_percent: float
    work_position: float
    buy_zone_threshold: float
    sell_zone_threshold: float
    buy_zone_active: bool
    sell_zone_active: bool
    micro_trend: str
    micro_trend_result: str
    action: str
    reason: str
    risk_allowed: bool
    risk_reason: str
    candidate_produced: bool
    risk_check_evaluated: bool
    order_attempted: bool
    data_source: str


@dataclass
class EntryZoneDebugSummary:
    total_iterations: int = 0
    buy_zone_active_count: int = 0
    sell_zone_active_count: int = 0
    no_zone_count: int = 0
    blocked_by_micro_trend_count: int = 0
    candidates_produced_count: int = 0
    risk_checks_evaluated_count: int = 0
    orders_attempted_count: int = 0


@dataclass
class EntryZoneDebugReportBuilder:
    config: BotConfig
    items: list[EntryZoneDebugItem] = field(default_factory=list)

    def add(self, item: dict) -> EntryZoneDebugItem:
        market_state = item["market_state"]
        action = item.get("action", "WAIT")
        reason = item.get("reason", "")
        buy_zone_active = market_state.work_position <= self.config.buy_zone_max
        sell_zone_active = market_state.work_position >= self.config.sell_zone_min
        reference_price = market_state.work_center
        deviation = market_state.price - reference_price
        deviation_percent = (deviation / reference_price * 100.0) if reference_price else 0.0
        candidate_produced = action in ENTRY_ACTIONS
        risk_check_evaluated = bool(item.get("risk_check_evaluated", candidate_produced))
        order_attempted = bool(item.get("order_attempted", False))

        debug_item = EntryZoneDebugItem(
            index=item["index"],
            timestamp=market_state.created_at.isoformat(),
            bid=market_state.bid,
            ask=market_state.ask,
            mid_price=(market_state.bid + market_state.ask) / 2.0,
            spread=market_state.spread,
            reference_price=reference_price,
            deviation_from_mean=deviation,
            deviation_from_mean_percent=deviation_percent,
            work_position=market_state.work_position,
            buy_zone_threshold=self.config.buy_zone_max,
            sell_zone_threshold=self.config.sell_zone_min,
            buy_zone_active=buy_zone_active,
            sell_zone_active=sell_zone_active,
            micro_trend=market_state.micro_trend,
            micro_trend_result=self._micro_trend_result(buy_zone_active, sell_zone_active, market_state.micro_trend),
            action=action,
            reason=reason,
            risk_allowed=bool(item.get("risk_allowed", False)),
            risk_reason=item.get("risk_reason", ""),
            candidate_produced=candidate_produced,
            risk_check_evaluated=risk_check_evaluated,
            order_attempted=order_attempted,
            data_source=item.get("data_source", "UNKNOWN"),
        )
        self.items.append(debug_item)
        return debug_item

    def summary(self) -> EntryZoneDebugSummary:
        summary = EntryZoneDebugSummary(total_iterations=len(self.items))
        for item in self.items:
            if item.buy_zone_active:
                summary.buy_zone_active_count += 1
            if item.sell_zone_active:
                summary.sell_zone_active_count += 1
            if not item.buy_zone_active and not item.sell_zone_active:
                summary.no_zone_count += 1
            if "micro trend not confirmed" in item.reason:
                summary.blocked_by_micro_trend_count += 1
            if item.candidate_produced:
                summary.candidates_produced_count += 1
            if item.risk_check_evaluated:
                summary.risk_checks_evaluated_count += 1
            if item.order_attempted:
                summary.orders_attempted_count += 1
        return summary

    def _micro_trend_result(self, buy_zone_active: bool, sell_zone_active: bool, micro_trend: str) -> str:
        if buy_zone_active:
            return "PASS" if micro_trend == "BUY_DOMINANT" else "FAIL"
        if sell_zone_active:
            return "PASS" if micro_trend == "SELL_DOMINANT" else "FAIL"
        return "N/A"
