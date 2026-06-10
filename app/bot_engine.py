from analytics.statistics_engine import StatisticsEngine
from app.app_logger import AppLogger
from audit.audit_engine import AuditEngine
from config.config_manager import ConfigManager
from health.health_check import HealthCheck
from market.binance_market_data_provider import BinanceMarketDataProvider
from market.market_analyzer import MarketAnalyzer
from market.market_data_cache import MarketDataCache
from notifications.notification_engine import NotificationEngine
from portfolio.bot_budget_manager import BotBudgetManager
from portfolio.portfolio_analytics import PortfolioAnalytics
from recovery.recovery_manager import RecoveryManager
from storage.database_manager import DatabaseManager
from state.bot_state_manager import BotState, BotStateManager
from strategy.decision_engine import DecisionEngine
from strategy.risk_manager import RiskManager
from trading.cycle_manager import CycleManager
from trading.demo_order_manager import DemoOrderManager
from trading.exchange_rules_engine import ExchangeRulesEngine
from trading.models import CycleStatus


class BotEngine:
    def __init__(self) -> None:
        self.config_manager = ConfigManager()
        self.config = self.config_manager.config
        self.logger = AppLogger(self.config).configure()

        self.database = DatabaseManager(self.config.database_path)
        self.market_data_cache = MarketDataCache(self.config.market_data_cache_ttl_seconds)
        self.market_data_provider = BinanceMarketDataProvider(
            base_url=self.config.binance_base_url,
            cache=self.market_data_cache,
        )
        self.market_analyzer = MarketAnalyzer(
            symbol=self.config.symbol,
            provider=self.market_data_provider,
            use_real_data=self.config.use_real_market_data,
            config=self.config,
            fallback_callback=self._save_market_data_fallback_event,
        )
        self.decision_engine = DecisionEngine(self.config)
        self.risk_manager = RiskManager(self.config)
        self.state_manager = BotStateManager(self.database)
        self.budget_manager = BotBudgetManager(self.database)
        self.cycle_manager = CycleManager()
        self.order_manager = DemoOrderManager()
        self.exchange_rules = ExchangeRulesEngine(self.config)
        self.portfolio_analytics = PortfolioAnalytics(self.database)
        self.statistics_engine = StatisticsEngine(self.database)
        self.notification_engine = NotificationEngine(self.database)
        self.audit_engine = AuditEngine(self.database)
        self.recovery_manager = RecoveryManager(self.database, self.cycle_manager)
        self.logger.info("BotEngine initialized")
        self.health_check = HealthCheck(
            config=self.config,
            database=self.database,
            market_provider=self.market_data_provider,
        )

    def _save_market_data_fallback_event(self, message: str) -> None:
        self.database.save_system_event(
            "WARNING",
            "MarketAnalyzer",
            f"Market data fallback activated: {message}",
        )

    def start(self) -> None:
        health_report = self.health_check.run()
        if not health_report.ok:
            failed = "; ".join(f"{item.name}: {item.message}" for item in health_report.failed_items)
            self.database.save_system_event("ERROR", "HealthCheck", failed)
            self.notification_engine.critical("Health Check failed", failed)
            self.logger.error("Health Check failed: %s", failed)
            print(f"Health Check failed: {failed}")
            return

        self.logger.info("Iteration started")
        self.database.save_system_event("INFO", "BotEngine", "USDT/USDC Bot MVP iteration started.")
        self.notification_engine.info("Bot iteration", "USDT/USDC Bot MVP iteration started.")
        if self.state_manager.current_state == BotState.INIT:
            self.state_manager.transition_to(BotState.RECOVERY, "Initial recovery before running")
        print("USDT/USDC Bot MVP started.")
        print(f"Configuration: symbol={self.config.symbol}, mode={self.config.mode}, target_profit={self.config.target_profit}")
        print(f"Exchange rules: tick={self.config.price_tick_size}, step={self.config.quantity_step_size}, min_notional={self.config.min_notional}")
        print(f"Market data cache TTL: {self.config.market_data_cache_ttl_seconds} sec")

        recovered = self.recovery_manager.recover_active_cycles()
        print(f"Recovered active cycles: {len(recovered)}")

        if self.state_manager.current_state == BotState.RECOVERY:
            self.state_manager.transition_to(BotState.READY, "Recovery completed")

        if self.cycle_manager.has_active_cycles():
            self.state_manager.transition_to(BotState.SAFE_WAIT, "Active cycle found after recovery")
            self.notification_engine.warning("Active cycle after recovery", "Unfinished cycle found. New cycles will not be opened.")
            print("Active cycle exists. New cycles will not be opened.")
            return

        if self.state_manager.current_state == BotState.READY:
            self.state_manager.transition_to(BotState.RUNNING_DEMO, "Starting Demo analysis cycle")

        market_state = self.market_analyzer.analyze_market()
        self.database.save_market_snapshot(market_state)

        budget = self.budget_manager.get_budget()
        decision = self.decision_engine.make_decision(market_state)
        risk_result = self.risk_manager.validate_decision(decision, budget, current_price=market_state.price)

        print(f"Symbol: {market_state.symbol}")
        print(f"Price: {market_state.price}")
        print(f"Bid: {market_state.bid}")
        print(f"Ask: {market_state.ask}")
        print(f"Spread: {market_state.spread}")
        print(f"Work Position: {market_state.work_position:.2f}%")
        print(f"Market Activity Score: {market_state.market_activity_score:.2f}")
        print(f"Market Regime: {market_state.market_regime}")
        print(f"OrderBook Pressure: {market_state.order_book_pressure} ({market_state.order_book_imbalance:.4f})")
        print(f"Micro Trend: {market_state.micro_trend} ({market_state.trade_volume_delta:.4f})")
        print(f"Volatility: {market_state.volatility_regime} ({market_state.relative_volatility:.8f})")
        print(f"Market Health: {market_state.market_health_status} ({market_state.market_health_score:.2f}) - {market_state.market_health_reason}")
        print(f"Budget USDT: {budget.usdt_budget:.2f}")
        print(f"Budget USDC: {budget.usdc_budget:.2f}")
        self.logger.info("Decision: %s | Risk allowed: %s | Reason: %s", decision.action, risk_result.allowed, decision.reason)
        print(f"Decision: {decision.action}")
        print(f"Reason: {decision.reason}")
        print(f"Risk allowed: {risk_result.allowed}")
        print(f"Risk reason: {risk_result.reason}")

        cycle_id = None

        if risk_result.allowed:
            trade_size = budget.total_value * self.config.trade_size_percent
            cycle = self.cycle_manager.create_cycle(
                mode="DEMO",
                direction=decision.action,
                current_price=market_state.price,
                amount=trade_size,
                target_profit=decision.target_profit,
            )
            cycle_id = cycle.id
            self.database.save_cycle(cycle)

            self.cycle_manager.place_open_order(cycle)
            self.database.save_cycle(cycle)
            self.database.save_system_event("INFO", "CycleManager", f"Demo cycle #{cycle.id} created", cycle.id)
            self.notification_engine.important("Demo cycle created", f"Demo cycle #{cycle.id} created: {cycle.direction.value}", cycle.id)

            print(f"Demo cycle #{cycle.id} created: {cycle.direction.value}")
            print(f"Open price: {cycle.open_price:.8f}")
            print(f"Close target: {cycle.close_price:.8f}")

            demo_market_path = [
                (market_state.bid, market_state.ask),
                (market_state.bid + 0.00005, market_state.ask + 0.00005),
                (cycle.close_price, cycle.close_price + 0.00001),
            ]

            for bid, ask in demo_market_path:
                if cycle.status == CycleStatus.OPEN_ORDER_PLACED:
                    if self.order_manager.can_fill_open_order(cycle, bid=bid, ask=ask):
                        self.cycle_manager.mark_open_filled(cycle)
                        self.database.save_cycle(cycle)
                        self.cycle_manager.place_close_order(cycle)
                        self.database.save_cycle(cycle)
                        self.database.save_system_event("INFO", "DemoOrderManager", "Open order filled", cycle.id)
                        print(f"Open order filled at bid={bid:.8f}, ask={ask:.8f}")

                if cycle.status == CycleStatus.CLOSE_ORDER_PLACED:
                    if self.order_manager.can_fill_close_order(cycle, bid=bid, ask=ask):
                        self.cycle_manager.mark_close_filled(cycle)
                        self.database.save_cycle(cycle)
                        self.database.save_system_event("INFO", "DemoOrderManager", "Close order filled", cycle.id)
                        print(f"Close order filled at bid={bid:.8f}, ask={ask:.8f}")
                        break

            if cycle.status == CycleStatus.CLOSED:
                self.notification_engine.important("Demo cycle closed", f"Profit: {cycle.actual_profit:.8f}", cycle.id)
                print(f"Demo cycle closed. Profit: {cycle.actual_profit:.8f}")
            else:
                print(f"Demo cycle is still open. Current status: {cycle.status.value}")

        self.database.save_trade_signal(decision, risk_result, cycle_id=cycle_id)
        self.audit_engine.audit_decision(market_state, decision, risk_result, cycle_id=cycle_id)

        print(f"Cycles in DB: {self.database.count_rows('cycles')}")
        print(f"Signals in DB: {self.database.count_rows('trade_signals')}")
        print(f"Market snapshots in DB: {self.database.count_rows('market_snapshots')}")
        print(f"System events in DB: {self.database.count_rows('system_events')}")

        stats = self.portfolio_analytics.calculate_stats(
            current_portfolio_value=budget.total_value + self.database.sum_realized_profit(),
        )

        print("--- Portfolio Analytics ---")
        print(f"Total cycles: {stats.total_cycles}")
        print(f"Closed cycles: {stats.closed_cycles}")
        print(f"Active cycles: {stats.active_cycles}")
        print(f"Win rate: {stats.win_rate * 100:.2f}%")
        print(f"Realized profit: {stats.realized_profit:.8f}")
        print(f"ROI: {stats.roi * 100:.4f}%")

        summary = self.statistics_engine.build_summary()

        print("--- Statistics Engine ---")
        print(f"Total signals: {summary.signal_stats.total_signals}")
        print(f"BUY signals: {summary.signal_stats.buy_signals}")
        print(f"SELL signals: {summary.signal_stats.sell_signals}")
        print(f"WAIT signals: {summary.signal_stats.wait_signals}")
        print(f"Allowed signals: {summary.signal_stats.allowed_signals}")
        print(f"Blocked signals: {summary.signal_stats.blocked_signals}")
        print(f"Average Cycle Prediction Score: {summary.signal_stats.average_cycle_prediction_score:.2f}")
        print(f"Average closed cycle duration: {summary.cycle_stats.average_duration_seconds:.2f} sec")

