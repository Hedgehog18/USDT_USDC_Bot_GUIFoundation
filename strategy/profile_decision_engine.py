from datetime import datetime

from config.config_manager import BotConfig
from market.models import MarketState
from strategy.decision_engine import DecisionEngine
from strategy.models import TradeDecision


SUPPORTED_RUNTIME_STRATEGY_PROFILES = ("strict_current", "mean_reversion_v1")


class StrategyProfileDecisionEngine:
    def __init__(self, config: BotConfig, profile: str = "strict_current") -> None:
        if profile not in SUPPORTED_RUNTIME_STRATEGY_PROFILES:
            supported = ", ".join(SUPPORTED_RUNTIME_STRATEGY_PROFILES)
            raise ValueError(f"Unsupported strategy profile: {profile}. Supported: {supported}")

        self.config = config
        self.profile = profile
        self.strict_engine = DecisionEngine(config)

    def make_decision(self, market_state: MarketState) -> TradeDecision:
        if self.profile == "strict_current":
            return self.strict_engine.make_decision(market_state)
        return self._mean_reversion_v1_decision(market_state)

    def _mean_reversion_v1_decision(self, market_state: MarketState) -> TradeDecision:
        if not (0.0 < market_state.spread <= self.config.max_allowed_spread):
            return self._decision("WAIT", "mean_reversion_v1: spread invalid", "LOW", 0.0)

        if (
            market_state.market_health_score < self.config.min_market_health_score
            or market_state.market_health_status == "UNHEALTHY"
        ):
            return self._decision("SAFE_WAIT", "mean_reversion_v1: market health invalid", "LOW", 0.0)

        if market_state.market_regime == "ABNORMAL":
            return self._decision("SAFE_WAIT", "mean_reversion_v1: abnormal market regime", "LOW", 0.0)

        if market_state.volatility_regime == "EXTREME":
            return self._decision("SAFE_WAIT", "mean_reversion_v1: extreme volatility", "LOW", 0.0)

        if market_state.work_position <= self.config.buy_zone_max:
            if market_state.micro_trend != "BUY_DOMINANT":
                return self._decision("WAIT", "mean_reversion_v1: BUY micro trend not confirmed", "LOW", 0.0)
            return self._decision(
                "BUY_USDC",
                "mean_reversion_v1: lower entry zone with BUY_DOMINANT micro trend",
                "MEDIUM",
                self._entry_score(market_state),
            )

        if market_state.work_position >= self.config.sell_zone_min:
            if market_state.micro_trend != "SELL_DOMINANT":
                return self._decision("WAIT", "mean_reversion_v1: SELL micro trend not confirmed", "LOW", 0.0)
            return self._decision(
                "SELL_USDC",
                "mean_reversion_v1: upper entry zone with SELL_DOMINANT micro trend",
                "MEDIUM",
                self._entry_score(market_state),
            )

        return self._decision("WAIT", "mean_reversion_v1: price outside entry zones", "LOW", 0.0)

    def _entry_score(self, market_state: MarketState) -> float:
        zone_depth = 100.0
        if self.config.buy_zone_max < market_state.work_position < self.config.sell_zone_min:
            zone_depth = 0.0
        return max(self.config.min_cycle_prediction_score, zone_depth)

    def _decision(self, action: str, reason: str, confidence: str, score: float) -> TradeDecision:
        return TradeDecision(
            action=action,
            reason=reason,
            confidence=confidence,
            cycle_prediction_score=score,
            recommended_trade_size=0.0,
            target_profit=self.config.target_profit,
            created_at=datetime.utcnow(),
        )
