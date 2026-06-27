from dataclasses import dataclass
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal

from app.bot_engine import BotEngine
from config.config_manager import BotConfig
from paper.models import PaperCycle
from paper.models import PaperCycleStatus
from paper.models import PaperOrderSide
from paper.models import PaperPortfolio
from paper.paper_cycle_manager import PaperCycleManager
from paper.paper_exchange import PaperExchange
from paper.paper_portfolio_manager import PaperPortfolioManager
from paper.paper_recovery_manager import PaperRecoveryManager
from paper.paper_state_manager import PaperState, PaperStateManager
from paper.paper_safety_engine import PaperSafetyEngine
from storage.database_manager import DatabaseManager


@dataclass(frozen=True)
class PaperTradingRunResult:
    iterations: int
    opened_cycles: int
    closed_cycles: int
    safety_stops: int
    final_portfolio: PaperPortfolio
    data_source: str = "UNKNOWN"


class PaperTradingEngine:
    """Orchestrator paper trading режиму.

    Виносить логіку з manage.py в окремий клас, щоб потім її можна було
    використати в GUI або сервісному runner без дублювання коду.
    """

    def __init__(
        self,
        config: BotConfig,
        database: DatabaseManager,
        bot: BotEngine | None = None,
        decision_debug_callback: Callable[[dict], None] | None = None,
        risk_debug_callback: Callable[[dict], None] | None = None,
        entry_zone_debug_callback: Callable[[dict], None] | None = None,
        close_debug_callback: Callable[[dict], None] | None = None,
        force_refresh_market_data: bool = False,
        strategy_profile: str = "strict_current",
    ) -> None:
        self.config = config
        self.database = database
        self.bot = bot or BotEngine()
        self.state_manager = PaperStateManager(database)
        self.recovery_manager = PaperRecoveryManager(database)

        self.portfolio_manager = PaperPortfolioManager(
            initial_usdt=config.backtest_initial_usdt,
            initial_usdc=config.backtest_initial_usdc,
        )
        self.exchange = PaperExchange(config, self.portfolio_manager)
        self.cycle_manager = PaperCycleManager(config, self.exchange)
        self.safety_engine = PaperSafetyEngine(config)
        self.decision_debug_callback = decision_debug_callback
        self.risk_debug_callback = risk_debug_callback
        self.entry_zone_debug_callback = entry_zone_debug_callback
        self.close_debug_callback = close_debug_callback
        self.force_refresh_market_data = force_refresh_market_data
        self.strategy_profile = strategy_profile

    def run(self, iterations: int) -> PaperTradingRunResult:
        if iterations <= 0:
            raise ValueError("iterations має бути більшим за 0.")

        if self.state_manager.current_state == PaperState.INIT:
            snapshot = self.recovery_manager.recover()
            self.state_manager.transition_to(PaperState.READY, f"Recovered paper snapshot: active_cycles={snapshot.active_cycles}, last_status={snapshot.last_cycle_status}")

        self.state_manager.transition_to(PaperState.RUNNING, "Paper trading run started")

        opened = 0
        closed = 0
        safety_stops = 0

        for index in range(iterations):
            if self.force_refresh_market_data:
                self._clear_market_data_cache()
            market_state = self.bot.market_analyzer.analyze_market()

            closed_from_database, has_database_open_cycles = self._process_database_open_cycles(
                current_price=market_state.price,
                index=index,
            )
            closed += closed_from_database
            if closed_from_database > 0:
                continue
            if has_database_open_cycles:
                if self.entry_zone_debug_callback:
                    self.entry_zone_debug_callback({
                        "index": index,
                        "market_state": market_state,
                        "action": "WAIT",
                        "reason": "database paper cycle is already open",
                        "risk_allowed": False,
                        "risk_reason": "Risk check skipped while database cycle is open",
                        "risk_check_evaluated": False,
                        "order_attempted": False,
                        "data_source": getattr(self.bot.market_analyzer, "last_data_source", "UNKNOWN"),
                    })
                continue

            portfolio = self.portfolio_manager.get_portfolio(market_state.price)

            recent_cycles = self.database.load_recent_paper_cycles(limit=20)
            safety = self.safety_engine.check(portfolio, recent_cycles)
            self.database.save_paper_safety_event(safety, portfolio.total_value)

            if not safety.allowed:
                safety_stops += 1
                self.state_manager.transition_to(PaperState.SAFE_STOP, safety.reason)
                break

            if self.cycle_manager.has_active_cycle():
                if self.entry_zone_debug_callback:
                    self.entry_zone_debug_callback({
                        "index": index,
                        "market_state": market_state,
                        "action": "WAIT",
                        "reason": "active paper cycle is already open",
                        "risk_allowed": False,
                        "risk_reason": "Risk check skipped while active cycle is open",
                        "risk_check_evaluated": False,
                        "order_attempted": False,
                        "data_source": getattr(self.bot.market_analyzer, "last_data_source", "UNKNOWN"),
                    })
                closed_cycle = self.cycle_manager.try_close_cycle(
                    market_state.price,
                    tolerance=self._close_tolerance_for_profile(self.strategy_profile),
                    rounding_digits=self._close_rounding_digits_for_profile(self.strategy_profile),
                    close_epsilon=self._close_epsilon_for_profile(self.strategy_profile),
                )
                if closed_cycle:
                    self.database.save_paper_cycle(closed_cycle, strategy_profile=self.strategy_profile)
                    closed += 1
                continue

            decision = self.bot.decision_engine.make_decision(market_state)
            risk = self.bot.risk_manager.validate_decision(
                decision,
                portfolio,
                current_price=market_state.price,
            )
            order_attempted = risk.allowed and decision.action in {"BUY_USDC", "SELL_USDC"}
            if self.entry_zone_debug_callback:
                self.entry_zone_debug_callback({
                    "index": index,
                    "market_state": market_state,
                    "action": decision.action,
                    "reason": decision.reason,
                    "risk_allowed": risk.allowed,
                    "risk_reason": risk.reason,
                    "risk_check_evaluated": decision.action in {"BUY_USDC", "SELL_USDC"},
                    "order_attempted": order_attempted,
                    "target_profit": decision.target_profit,
                    "data_source": getattr(self.bot.market_analyzer, "last_data_source", "UNKNOWN"),
                })
            if self.decision_debug_callback and self._is_potential_entry_state(market_state):
                self.decision_debug_callback({
                    "index": index,
                    "market_state": market_state,
                    "work_position": market_state.work_position,
                    "action": decision.action,
                    "reason": decision.reason,
                    "risk_allowed": risk.allowed,
                    "risk_reason": risk.reason,
                    "data_source": getattr(self.bot.market_analyzer, "last_data_source", "UNKNOWN"),
                    "market_debug_info": getattr(self.bot.market_analyzer, "last_debug_info", {}),
                })
            if self.risk_debug_callback and decision.action in {"BUY_USDC", "SELL_USDC"}:
                self.risk_debug_callback({
                    "index": index,
                    "market_state": market_state,
                    "decision": decision,
                    "risk": risk,
                    "portfolio": portfolio,
                })

            if not risk.allowed or decision.action not in {"BUY_USDC", "SELL_USDC"}:
                continue

            opened_cycle = self.cycle_manager.open_cycle(
                direction=decision.action,
                price=market_state.price,
                target_profit=decision.target_profit,
            )
            if opened_cycle:
                self.database.save_paper_cycle(opened_cycle, strategy_profile=self.strategy_profile)
                opened += 1

        if self.state_manager.current_state == PaperState.RUNNING:
            self.state_manager.transition_to(PaperState.READY, "Paper trading run finished")

        return PaperTradingRunResult(
            iterations=iterations,
            opened_cycles=opened,
            closed_cycles=closed,
            safety_stops=safety_stops,
            final_portfolio=self.portfolio_manager.get_portfolio(),
            data_source=getattr(self.bot.market_analyzer, "last_data_source", "UNKNOWN"),
        )

    def _is_potential_entry_state(self, market_state) -> bool:
        return (
            market_state.work_position <= self.config.buy_zone_max
            or market_state.work_position >= self.config.sell_zone_min
        )

    def _process_database_open_cycles(self, current_price: float, index: int) -> tuple[int, bool]:
        rows = self.database.load_open_paper_cycles(limit=1000)
        if not rows:
            return 0, False

        closed_count = 0
        open_cycles_remaining = False
        for row in rows:
            cycle, strategy_profile, cycle_id = self._paper_cycle_from_open_row(row)
            target_price = cycle.close_price
            close_tolerance = self._close_tolerance_for_profile(strategy_profile)
            close_rounding_digits = self._close_rounding_digits_for_profile(strategy_profile)
            close_epsilon = self._close_epsilon_for_profile(strategy_profile)
            target_close_condition_met = self.cycle_manager.can_close_cycle(
                cycle,
                current_price,
                tolerance=close_tolerance,
                rounding_digits=close_rounding_digits,
                close_epsilon=close_epsilon,
            )
            max_holding_limit = self._max_holding_seconds_for_profile(strategy_profile)
            cycle_age = self._cycle_age_seconds(cycle)
            max_holding_condition_met = (
                max_holding_limit is not None
                and cycle_age >= max_holding_limit
            )
            close_condition_met = target_close_condition_met or max_holding_condition_met
            close_reason = "target" if target_close_condition_met else self._max_holding_close_reason(strategy_profile)

            if not close_condition_met:
                open_cycles_remaining = True
                self._emit_close_debug({
                    "index": index,
                    "db_id": cycle.id,
                    "cycle_id": cycle_id,
                    "strategy_profile": strategy_profile,
                    "direction": cycle.direction.value,
                    "current_price": current_price,
                    "target_price": target_price,
                    **self._close_debug_price_fields(
                        current_price,
                        target_price,
                        close_rounding_digits,
                        close_epsilon,
                    ),
                    "close_tolerance": close_tolerance,
                    "close_rounding_digits": close_rounding_digits,
                    "close_condition_met": False,
                    "target_close_condition_met": False,
                    "max_holding_limit": max_holding_limit,
                    "cycle_age": cycle_age,
                    "max_holding_condition_met": False,
                    "close_attempted": False,
                    "close_result": "SKIPPED",
                    "close_reason": None,
                    "reason": "Close condition is not met.",
                })
                continue

            closed_cycle = self.cycle_manager.close_cycle(cycle, current_price)
            setattr(closed_cycle, "close_reason", close_reason)
            self.database.save_paper_cycle(closed_cycle, strategy_profile=strategy_profile)
            if closed_cycle.status == PaperCycleStatus.CLOSED:
                closed_count += 1
                result = "CLOSED"
                reason = f"Cycle closed successfully by {close_reason}."
            else:
                result = closed_cycle.status.value
                reason = "Close order was not filled."

            self._emit_close_debug({
                "index": index,
                "db_id": closed_cycle.id,
                "cycle_id": cycle_id,
                "strategy_profile": strategy_profile,
                "direction": closed_cycle.direction.value,
                "current_price": current_price,
                "target_price": target_price,
                **self._close_debug_price_fields(
                    current_price,
                    target_price,
                    close_rounding_digits,
                    close_epsilon,
                ),
                "close_tolerance": close_tolerance,
                "close_rounding_digits": close_rounding_digits,
                "close_condition_met": True,
                "target_close_condition_met": target_close_condition_met,
                "max_holding_limit": max_holding_limit,
                "cycle_age": cycle_age,
                "max_holding_condition_met": max_holding_condition_met,
                "close_attempted": True,
                "close_result": result,
                "close_reason": close_reason,
                "reason": reason,
            })

        return closed_count, open_cycles_remaining

    def _paper_cycle_from_open_row(self, row: tuple) -> tuple[PaperCycle, str, int]:
        (
            db_id,
            _timestamp,
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
        ) = row

        cycle = PaperCycle(
            id=int(db_id),
            direction=PaperOrderSide(direction),
            status=PaperCycleStatus(status),
            open_price=float(open_price),
            close_price=float(close_price),
            quantity=float(quantity),
            open_fee=float(open_fee),
            close_fee=float(close_fee),
            gross_profit=float(gross_profit),
            net_profit=float(net_profit),
            opened_at=datetime.fromisoformat(opened_at),
            closed_at=datetime.fromisoformat(closed_at) if closed_at else None,
        )
        return cycle, str(strategy_profile), int(cycle_id)

    def _close_tolerance_for_profile(self, strategy_profile: str) -> float:
        return 0.0

    def _close_rounding_digits_for_profile(self, strategy_profile: str) -> int | None:
        return None

    def _close_epsilon_for_profile(self, strategy_profile: str) -> Decimal:
        if strategy_profile == "mean_reversion_v2_small_target":
            return Decimal("0.00000010")
        return Decimal("0")

    def _max_holding_seconds_for_profile(self, strategy_profile: str) -> float | None:
        if strategy_profile == "mean_reversion_hf_micro_v1":
            return 270.0
        return None

    def _max_holding_close_reason(self, strategy_profile: str) -> str | None:
        if strategy_profile == "mean_reversion_hf_micro_v1":
            return "max_holding_270s"
        return None

    @staticmethod
    def _cycle_age_seconds(cycle: PaperCycle) -> float:
        return max(0.0, (datetime.utcnow() - cycle.opened_at).total_seconds())

    @staticmethod
    def _close_debug_price_fields(
        current_price: float,
        target_price: float,
        rounding_digits: int | None,
        close_epsilon: Decimal | float,
    ) -> dict:
        epsilon = Decimal(str(close_epsilon))
        return {
            "current_price_raw": current_price,
            "target_price_raw": target_price,
            "current_price_rounded": (
                round(current_price, rounding_digits)
                if rounding_digits is not None
                else current_price
            ),
            "target_price_rounded": (
                round(target_price, rounding_digits)
                if rounding_digits is not None
                else target_price
            ),
            "close_rounding_decimals": rounding_digits,
            "close_epsilon": float(epsilon),
            "effective_buy_close_price": float(Decimal(str(current_price)) + epsilon),
            "effective_sell_close_price": float(Decimal(str(current_price)) - epsilon),
        }

    def _emit_close_debug(self, payload: dict) -> None:
        if self.close_debug_callback:
            self.close_debug_callback(payload)

    def _clear_market_data_cache(self) -> None:
        cache = getattr(self.bot, "market_data_cache", None)
        clear = getattr(cache, "clear", None)
        if callable(clear):
            clear()

        provider = getattr(getattr(self.bot, "market_analyzer", None), "provider", None)
        provider_cache = getattr(provider, "cache", None)
        provider_clear = getattr(provider_cache, "clear", None)
        if callable(provider_clear):
            provider_clear()
