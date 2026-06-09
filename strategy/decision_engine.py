from datetime import datetime

from config.config_manager import BotConfig
from market.models import MarketState
from strategy.models import TradeDecision


class DecisionEngine:
    def __init__(self, config: BotConfig) -> None:
        self.config = config

    def make_decision(self, market_state: MarketState) -> TradeDecision:
        if market_state.market_regime == "ABNORMAL":
            return self._decision("SAFE_WAIT", "Abnormal market state", "LOW", 0)

        if market_state.market_health_status == "UNHEALTHY":
            return self._decision(
                "SAFE_WAIT",
                f"Market health unhealthy: {market_state.market_health_reason}",
                "LOW",
                market_state.market_health_score,
            )

        if market_state.center_confidence == "LOW":
            return self._decision("WAIT", "Low center confidence", "LOW", 0)

        if market_state.market_activity_score < self.config.min_market_activity_score:
            return self._decision("WAIT", "Low market activity", "LOW", market_state.market_activity_score)

        score = self._calculate_cycle_prediction_score(market_state)

        if market_state.work_position <= self.config.buy_zone_max:
            action = "BUY_USDC"
            reason = "Price is in the lower part of the working corridor"
        elif market_state.work_position >= self.config.sell_zone_min:
            action = "SELL_USDC"
            reason = "Price is in the upper part of the working corridor"
        else:
            return self._decision("WAIT", "Price is close to the working corridor center", "MEDIUM", score)

        microstructure_score = self._microstructure_score(market_state, action)
        score = score * 0.80 + microstructure_score * 0.20

        if market_state.volatility_regime == "EXTREME":
            return self._decision("SAFE_WAIT", "Extreme volatility", "LOW", score)

        if score < self.config.min_cycle_prediction_score:
            return self._decision(
                "WAIT",
                "Insufficient Cycle Prediction Score after microstructure filters",
                "MEDIUM",
                score,
            )

        confidence = "HIGH" if score >= 80 else "MEDIUM"
        reason = f"{reason}; microstructure={microstructure_score:.2f}; volatility={market_state.volatility_regime}"
        return self._decision(action, reason, confidence, score)

    def _calculate_cycle_prediction_score(self, market_state: MarketState) -> float:
        position_score = self._position_score(market_state.work_position)
        short_position_score = self._secondary_position_score(market_state.short_position)
        long_position_score = self._long_position_score(market_state.long_position)
        center_score = {"HIGH": 100.0, "MEDIUM": 70.0, "LOW": 0.0}.get(market_state.center_confidence, 0.0)
        regime_score = {"QUIET": 20.0, "NORMAL": 70.0, "ACTIVE": 90.0, "VOLATILE": 60.0, "ABNORMAL": 0.0}.get(market_state.market_regime, 50.0)
        score = (
            position_score * 0.25
            + short_position_score * 0.12
            + long_position_score * 0.08
            + market_state.market_activity_score * 0.18
            + center_score * 0.12
            + regime_score * 0.10
            + self._volatility_score(market_state) * 0.15
        )
        return max(0.0, min(100.0, score))

    @staticmethod
    def _position_score(position: float) -> float:
        if position <= 20 or position >= 80:
            return 100.0
        if 20 < position < 40 or 60 < position < 80:
            return 70.0
        return 30.0

    @staticmethod
    def _secondary_position_score(position: float) -> float:
        if position <= 35 or position >= 65:
            return 100.0
        if 35 < position < 45 or 55 < position < 65:
            return 60.0
        return 30.0

    @staticmethod
    def _long_position_score(position: float) -> float:
        if 20 <= position <= 80:
            return 100.0
        if 10 <= position < 20 or 80 < position <= 90:
            return 70.0
        return 40.0


    def _microstructure_score(self, market_state: MarketState, action: str) -> float:
        """Score signal confirmation from order book and recent trades."""
        if action == "BUY_USDC":
            return self._buy_microstructure_score(market_state)

        if action == "SELL_USDC":
            return self._sell_microstructure_score(market_state)

        return 50.0

    @staticmethod
    def _buy_microstructure_score(market_state: MarketState) -> float:
        score = 50.0

        if market_state.order_book_pressure == "BID_PRESSURE":
            score += 20.0
        elif market_state.order_book_pressure == "ASK_PRESSURE":
            score -= 20.0

        if market_state.micro_trend == "BUY_DOMINANT":
            score += 20.0
        elif market_state.micro_trend == "SELL_DOMINANT":
            score -= 20.0

        return max(0.0, min(100.0, score))

    @staticmethod
    def _sell_microstructure_score(market_state: MarketState) -> float:
        score = 50.0

        if market_state.order_book_pressure == "ASK_PRESSURE":
            score += 20.0
        elif market_state.order_book_pressure == "BID_PRESSURE":
            score -= 20.0

        if market_state.micro_trend == "SELL_DOMINANT":
            score += 20.0
        elif market_state.micro_trend == "BUY_DOMINANT":
            score -= 20.0

        return max(0.0, min(100.0, score))

    @staticmethod
    def _volatility_score(market_state: MarketState) -> float:
        scores = {
            "LOW": 70.0,
            "NORMAL": 100.0,
            "HIGH": 60.0,
            "EXTREME": 10.0,
            "UNKNOWN": 50.0,
        }
        return scores.get(market_state.volatility_regime, 50.0)

    def _decision(self, action: str, reason: str, confidence: str, score: float) -> TradeDecision:
        return TradeDecision(
            action=action,
            reason=reason,
            confidence=confidence,
            cycle_prediction_score=score,
            recommended_trade_size=0,
            target_profit=self.config.target_profit,
            created_at=datetime.utcnow(),
        )
