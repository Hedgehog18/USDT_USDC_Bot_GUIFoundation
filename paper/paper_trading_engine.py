from dataclasses import dataclass
from collections.abc import Callable

from app.bot_engine import BotEngine
from config.config_manager import BotConfig
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
        force_refresh_market_data: bool = False,
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
        self.force_refresh_market_data = force_refresh_market_data

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
            portfolio = self.portfolio_manager.get_portfolio(market_state.price)

            recent_cycles = self.database.load_recent_paper_cycles(limit=20)
            safety = self.safety_engine.check(portfolio, recent_cycles)
            self.database.save_paper_safety_event(safety, portfolio.total_value)

            if not safety.allowed:
                safety_stops += 1
                self.state_manager.transition_to(PaperState.SAFE_STOP, safety.reason)
                break

            if self.cycle_manager.has_active_cycle():
                closed_cycle = self.cycle_manager.try_close_cycle(market_state.price)
                if closed_cycle:
                    self.database.save_paper_cycle(closed_cycle)
                    closed += 1
                continue

            decision = self.bot.decision_engine.make_decision(market_state)
            risk = self.bot.risk_manager.validate_decision(
                decision,
                portfolio,
                current_price=market_state.price,
            )
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
            )
            if opened_cycle:
                self.database.save_paper_cycle(opened_cycle)
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
