from config.config_manager import BotConfig
from backtest.backtest_metrics_engine import BacktestMetricsEngine
from backtest.models import BacktestResult, BacktestTrade
from backtest.historical_data_provider import HistoricalCandle
from market.activity_engine import ActivityEngine
from market.center_engine import CenterEngine
from market.models import MarketState
from portfolio.models import BotBudget
from strategy.decision_engine import DecisionEngine
from strategy.risk_manager import RiskManager
from trading.fee_engine import FeeEngine


class BacktestEngine:
    """Перший MVP backtest.

    Спрощення:
    - використовує close prices як історичний ряд;
    - симулює вхід і вихід за target_profit;
    - не моделює чергу ордерів;
    - не моделює часткові виконання;
    - потрібен для первинної перевірки логіки сигналів.
    """

    def __init__(self, config: BotConfig, decision_engine=None) -> None:
        self.config = config
        self.center_engine = CenterEngine()
        self.activity_engine = ActivityEngine()
        self.decision_engine = decision_engine or DecisionEngine(config)
        self.risk_manager = RiskManager(config)
        self.fee_engine = FeeEngine(config)
        self.metrics_engine = BacktestMetricsEngine()
        self.last_equity_curve: list[float] = []

    def run(self, candles: list[HistoricalCandle]) -> tuple[BacktestResult, list[BacktestTrade]]:
        if len(candles) < 30:
            self.last_equity_curve = []
            return self._empty_result(len(candles)), []

        usdt = self.config.backtest_initial_usdt
        usdc = self.config.backtest_initial_usdc
        initial_value = usdt + usdc
        equity_curve = [initial_value]

        trades: list[BacktestTrade] = []
        signals = 0

        closes = [c.close for c in candles]

        for index in range(30, len(candles) - 1):
            window = closes[max(0, index - 30):index]
            current_price = closes[index]

            state = self._build_state(
                current_price=current_price,
                prices=window,
            )

            decision = self.decision_engine.make_decision(state)
            if decision.action in {"BUY_USDC", "SELL_USDC"}:
                signals += 1

            budget = BotBudget(
                usdt_budget=usdt,
                usdc_budget=usdc,
                usdc_price=current_price,
            )
            risk = self.risk_manager.validate_decision(
                decision,
                budget,
                current_price=current_price,
            )

            if not risk.allowed:
                equity_curve.append(usdt + usdc * current_price)
                continue

            trade_value = (usdt + usdc * current_price) * self.config.trade_size_percent
            quantity = trade_value / current_price
            exit_price = self._find_exit_price(
                candles=candles,
                start_index=index + 1,
                action=decision.action,
                entry_price=current_price,
                target_profit=decision.target_profit,
            )

            if exit_price is None:
                equity_curve.append(usdt + usdc * current_price)
                continue

            profit = self.fee_engine.calculate_profit(
                direction=decision.action,
                open_price=current_price,
                close_price=exit_price,
                quantity=quantity,
            )

            if decision.action == "BUY_USDC":
                usdt -= trade_value
                usdc += quantity
                usdc -= quantity
                usdt += quantity * exit_price - profit.fees.total_fee
            else:
                usdc -= quantity
                usdt += trade_value
                usdt -= quantity * exit_price + profit.fees.total_fee
                usdc += quantity

            trades.append(
                BacktestTrade(
                    index=index,
                    action=decision.action,
                    entry_price=current_price,
                    exit_price=exit_price,
                    quantity=quantity,
                    gross_profit=profit.gross_profit,
                    fees=profit.fees.total_fee,
                    net_profit=profit.net_profit,
                )
            )

            equity_curve.append(usdt + usdc * exit_price)

        self.last_equity_curve = equity_curve

        result = self._build_result(
            candles=candles,
            trades=trades,
            signals=signals,
            initial_value=initial_value,
            final_value=equity_curve[-1] if equity_curve else initial_value,
            equity_curve=equity_curve,
        )
        return result, trades

    def _build_state(self, current_price: float, prices: list[float]) -> MarketState:
        if not prices:
            prices = [current_price]

        work_prices = prices[-15:] if len(prices) >= 15 else prices
        short_prices = prices[-30:] if len(prices) >= 30 else prices
        long_prices = prices

        work = self.center_engine.build_corridor(work_prices, current_price)
        short = self.center_engine.build_corridor(short_prices, current_price)
        long = self.center_engine.build_corridor(long_prices, current_price)

        center_confidence = self.center_engine.calculate_center_confidence(
            work.active_center,
            short.active_center,
            long.active_center,
            range_value=short.range_value,
        )
        center_alignment = self.center_engine.calculate_center_alignment(
            work.active_center,
            short.active_center,
            long.active_center,
        )

        spreads = [self.config.price_tick_size for _ in work_prices]
        activity = self.activity_engine.calculate_activity_metrics(
            work_prices,
            spreads,
            work.active_center,
        )

        return MarketState(
            symbol=self.config.symbol,
            price=current_price,
            bid=current_price - self.config.price_tick_size,
            ask=current_price + self.config.price_tick_size,
            spread=self.config.price_tick_size * 2,
            work_low=work.low,
            work_high=work.high,
            work_center=work.active_center,
            work_position=work.position,
            short_low=short.low,
            short_high=short.high,
            short_center=short.active_center,
            short_position=short.position,
            long_low=long.low,
            long_high=long.high,
            long_center=long.active_center,
            long_position=long.position,
            center_confidence=center_confidence,
            center_alignment=center_alignment,
            tick_activity_score=activity.tick_activity_score,
            center_crossing_score=activity.center_crossing_score,
            mean_reversion_score=activity.mean_reversion_score,
            spread_stability_score=activity.spread_stability_score,
            corridor_quality_score=activity.corridor_quality_score,
            market_activity_score=activity.market_activity_score,
            market_regime="NORMAL",
            order_book_imbalance=0.0,
            order_book_pressure="BALANCED",
            trade_volume_delta=0.0,
            micro_trend="NEUTRAL",
            relative_volatility=0.0,
            volatility_regime="NORMAL",
            market_health_score=100.0,
            market_health_status="HEALTHY",
            market_health_reason="Backtest synthetic state",
            created_at=__import__("datetime").datetime.utcnow(),
        )

    @staticmethod
    def _find_exit_price(
        candles: list[HistoricalCandle],
        start_index: int,
        action: str,
        entry_price: float,
        target_profit: float,
    ) -> float | None:
        if action == "BUY_USDC":
            target = entry_price * (1 + target_profit)
            for candle in candles[start_index:]:
                if candle.high >= target:
                    return target

        if action == "SELL_USDC":
            target = entry_price * (1 - target_profit)
            for candle in candles[start_index:]:
                if candle.low <= target:
                    return target

        return None

    def _build_result(
        self,
        candles: list[HistoricalCandle],
        trades: list[BacktestTrade],
        signals: int,
        initial_value: float,
        final_value: float,
        equity_curve: list[float],
    ) -> BacktestResult:
        winning = sum(1 for trade in trades if trade.net_profit > 0)
        losing = sum(1 for trade in trades if trade.net_profit <= 0)
        gross_profit = sum(trade.gross_profit for trade in trades)
        fees = sum(trade.fees for trade in trades)
        net_profit = sum(trade.net_profit for trade in trades)
        advanced_metrics = self.metrics_engine.calculate(trades, equity_curve)

        return BacktestResult(
            symbol=self.config.symbol,
            interval=self.config.backtest_interval,
            candles=len(candles),
            signals=signals,
            trades=len(trades),
            winning_trades=winning,
            losing_trades=losing,
            win_rate=(winning / len(trades)) if trades else 0.0,
            gross_profit=gross_profit,
            total_fees=fees,
            net_profit=net_profit,
            roi=(net_profit / initial_value) if initial_value > 0 else 0.0,
            final_value=final_value,
            max_drawdown=self._max_drawdown(equity_curve),
            sharpe_ratio=advanced_metrics.sharpe_ratio,
            sortino_ratio=advanced_metrics.sortino_ratio,
            profit_factor=advanced_metrics.profit_factor,
            expectancy=advanced_metrics.expectancy,
        )

    def _empty_result(self, candles_count: int) -> BacktestResult:
        initial = self.config.backtest_initial_usdt + self.config.backtest_initial_usdc
        return BacktestResult(
            symbol=self.config.symbol,
            interval=self.config.backtest_interval,
            candles=candles_count,
            signals=0,
            trades=0,
            winning_trades=0,
            losing_trades=0,
            win_rate=0.0,
            gross_profit=0.0,
            total_fees=0.0,
            net_profit=0.0,
            roi=0.0,
            final_value=initial,
            max_drawdown=0.0,
            sharpe_ratio=0.0,
            sortino_ratio=0.0,
            profit_factor=0.0,
            expectancy=0.0,
        )

    @staticmethod
    def _max_drawdown(equity_curve: list[float]) -> float:
        if not equity_curve:
            return 0.0

        peak = equity_curve[0]
        max_dd = 0.0

        for value in equity_curve:
            if value > peak:
                peak = value

            if peak > 0:
                dd = (peak - value) / peak
                max_dd = max(max_dd, dd)

        return max_dd
