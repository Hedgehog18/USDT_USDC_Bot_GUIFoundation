from datetime import datetime
from typing import Callable

from config.config_manager import BotConfig
from market.activity_engine import ActivityEngine
from market.binance_market_data_provider import BinanceMarketDataError, BinanceMarketDataProvider
from market.center_engine import CenterEngine
from market.models import MarketState
from market.order_book_engine import OrderBookEngine
from market.trade_history_engine import TradeHistoryEngine
from market.volatility_engine import VolatilityEngine
from market.market_health_engine import MarketHealthEngine


class MarketAnalyzer:
    def __init__(
        self,
        symbol: str = "USDCUSDT",
        provider: BinanceMarketDataProvider | None = None,
        use_real_data: bool = True,
        config: BotConfig | None = None,
        fallback_callback: Callable[[str], None] | None = None,
    ) -> None:
        self.symbol = symbol
        self.config = config
        self.center_engine = CenterEngine()
        self.activity_engine = ActivityEngine()
        self.order_book_engine = OrderBookEngine()
        self.trade_history_engine = TradeHistoryEngine()
        self.volatility_engine = VolatilityEngine()
        self.market_health_engine = MarketHealthEngine(config) if config else None
        self.provider = provider or BinanceMarketDataProvider()
        self.use_real_data = use_real_data
        self.fallback_callback = fallback_callback
        self.last_data_source = "UNKNOWN"
        self.last_fallback_error = ""

    def analyze_market(self) -> MarketState:
        if self.use_real_data:
            try:
                state = self._analyze_real_market()
                self.last_data_source = "BINANCE"
                self.last_fallback_error = ""
                return state
            except BinanceMarketDataError as exc:
                # Тимчасовий fallback, щоб Demo не падав при відсутності інтернету.
                self.last_data_source = "FALLBACK"
                self.last_fallback_error = str(exc)
                self._notify_fallback(str(exc))
                return self._analyze_mock_market()

        self.last_data_source = "MOCK"
        self.last_fallback_error = ""
        return self._analyze_mock_market()

    def _notify_fallback(self, message: str) -> None:
        if self.fallback_callback is None:
            return

        try:
            self.fallback_callback(message)
        except Exception:
            pass

    def _analyze_real_market(self) -> MarketState:
        bid_ask = self.provider.get_bid_ask(self.symbol)

        work_prices = self.provider.get_kline_closes(self.symbol, "1m", 15).closes
        short_prices = self.provider.get_kline_closes(self.symbol, "1m", 60).closes
        long_prices = self.provider.get_kline_closes(self.symbol, "15m", 96).closes
        order_book = self.provider.get_order_book(self.symbol, 20)
        recent_trades = self.provider.get_recent_trades(self.symbol, 50)

        current_price = bid_ask.mid_price
        spreads = [bid_ask.spread] * max(5, min(len(work_prices), 20))

        return self._build_market_state(
            current_price=current_price,
            bid=bid_ask.bid,
            ask=bid_ask.ask,
            spread=bid_ask.spread,
            work_prices=work_prices,
            short_prices=short_prices,
            long_prices=long_prices,
            spreads=spreads,
            order_book=order_book,
            recent_trades=recent_trades,
        )

    def _analyze_mock_market(self) -> MarketState:
        current_price = 0.99992

        work_prices = [
            0.99990, 0.99995, 1.00000, 1.00002, 1.00005,
            1.00002, 0.99998, 0.99994, 1.00001, 1.00003,
        ]
        short_prices = [0.99985, 0.99990, 1.00000, 1.00004, 1.00008]
        long_prices = [0.99970, 0.99985, 1.00000, 1.00010, 1.00020]
        spreads = [0.00002, 0.00002, 0.00003, 0.00002, 0.00002]

        return self._build_market_state(
            current_price=current_price,
            bid=current_price - 0.00001,
            ask=current_price,
            spread=0.00001,
            work_prices=work_prices,
            short_prices=short_prices,
            long_prices=long_prices,
            spreads=spreads,
        )

    def _build_market_state(
        self,
        current_price: float,
        bid: float,
        ask: float,
        spread: float,
        work_prices: list[float],
        short_prices: list[float],
        long_prices: list[float],
        spreads: list[float],
        order_book=None,
        recent_trades=None,
    ) -> MarketState:
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

        activity = self.activity_engine.calculate_activity_metrics(
            work_prices,
            spreads,
            work.active_center,
        )

        market_regime = self._classify_market_regime(activity.market_activity_score)

        order_book_metrics = self.order_book_engine.analyze(order_book) if order_book else None
        trade_metrics = self.trade_history_engine.analyze(recent_trades or [])
        volatility_metrics = self.volatility_engine.analyze(work_prices)
        market_health = None
        if self.market_health_engine:
            market_health = self.market_health_engine.analyze(
                spread=spread,
                volatility_regime=volatility_metrics.volatility_regime,
                order_book_metrics=order_book_metrics,
            )

        return MarketState(
            symbol=self.symbol,
            price=current_price,
            bid=bid,
            ask=ask,
            spread=spread,
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
            market_regime=market_regime,
            order_book_imbalance=order_book_metrics.imbalance if order_book_metrics else 0.0,
            order_book_pressure=order_book_metrics.pressure if order_book_metrics else "UNKNOWN",
            trade_volume_delta=trade_metrics.volume_delta,
            micro_trend=trade_metrics.micro_trend,
            relative_volatility=volatility_metrics.relative_volatility,
            volatility_regime=volatility_metrics.volatility_regime,
            market_health_score=market_health.score if market_health else 100.0,
            market_health_status=market_health.status if market_health else "HEALTHY",
            market_health_reason=market_health.reason if market_health else "MarketHealthEngine disabled",
            created_at=datetime.utcnow(),
        )

    @staticmethod
    def _classify_market_regime(score: float) -> str:
        if score < 20:
            return "QUIET"
        if score < 60:
            return "NORMAL"
        if score < 80:
            return "ACTIVE"
        return "VOLATILE"
