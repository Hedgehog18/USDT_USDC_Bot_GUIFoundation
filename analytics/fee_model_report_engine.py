from dataclasses import dataclass

from config.config_manager import BotConfig
from trading.exchange_rules_engine import ExchangeRulesEngine
from trading.fee_engine import FeeEngine


@dataclass(frozen=True)
class FeeScenario:
    name: str
    open_fee_rate: float
    close_fee_rate: float
    open_fee: float
    close_fee: float
    total_fee: float
    gross_profit: float
    net_profit: float


@dataclass(frozen=True)
class FeeModelReport:
    maker_fee: float
    taker_fee: float
    backtest_model: str
    paper_model: str
    risk_profitability_model: str
    scenarios: list[FeeScenario]
    risk_example_estimated_fees: float
    observed_fee_rate_interpretation: str
    fee_model_source: list[str]
    fee_model_consistency: str
    notes: list[str]


class FeeModelReportEngine:
    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self.fee_engine = FeeEngine(config)
        self.exchange_rules = ExchangeRulesEngine(config)

    def build_report(
        self,
        trade_size: float = 10.0,
        open_price: float = 1.0,
        observed_estimated_fees: float = 0.02001119,
    ) -> FeeModelReport:
        close_price = open_price * (1 + self.config.target_profit)
        quantity = trade_size / open_price

        scenarios = [
            self._scenario("maker/maker", self.config.maker_fee_percent, self.config.maker_fee_percent, open_price, close_price, quantity),
            self._scenario("maker/taker", self.config.maker_fee_percent, self.config.taker_fee_percent, open_price, close_price, quantity),
            self._scenario("taker/taker", self.config.taker_fee_percent, self.config.taker_fee_percent, open_price, close_price, quantity),
        ]

        risk = self.exchange_rules.check_profitability_after_rounding(
            direction="BUY_USDC",
            open_price=open_price,
            close_price=close_price,
            budget_value=trade_size,
        )

        consistency = "MISMATCH"

        return FeeModelReport(
            maker_fee=self.config.maker_fee_percent,
            taker_fee=self.config.taker_fee_percent,
            backtest_model="FeeEngine.calculate_profit(..., use_taker_fee=False) -> maker fee for both legs",
            paper_model="PaperExchange market orders use taker fee; PaperCycleManager close PnL uses use_taker_fee=True",
            risk_profitability_model="ExchangeRulesEngine.check_profitability_after_rounding uses maker_fee_percent for open+close notional",
            scenarios=scenarios,
            risk_example_estimated_fees=risk.estimated_fees,
            observed_fee_rate_interpretation=self._interpret_observed_fees(observed_estimated_fees),
            fee_model_source=[
                "config/settings.json: maker_fee_percent, taker_fee_percent",
                "config/config_manager.py: BotConfig.maker_fee_percent / taker_fee_percent",
                "trading/fee_engine.py: FeeEngine.calculate_fees",
                "trading/exchange_rules_engine.py: ExchangeRulesEngine.check_profitability_after_rounding",
                "paper/paper_exchange.py: PaperExchange.execute_market_order",
                "paper/paper_cycle_manager.py: PaperCycleManager.try_close_cycle",
                "backtest/backtest_engine.py: BacktestEngine.run",
            ],
            fee_model_consistency=consistency,
            notes=self._notes(consistency),
        )

    def _scenario(
        self,
        name: str,
        open_fee_rate: float,
        close_fee_rate: float,
        open_price: float,
        close_price: float,
        quantity: float,
    ) -> FeeScenario:
        open_notional = open_price * quantity
        close_notional = close_price * quantity
        open_fee = open_notional * open_fee_rate
        close_fee = close_notional * close_fee_rate
        gross_profit = (close_price - open_price) * quantity
        total_fee = open_fee + close_fee

        return FeeScenario(
            name=name,
            open_fee_rate=open_fee_rate,
            close_fee_rate=close_fee_rate,
            open_fee=open_fee,
            close_fee=close_fee,
            total_fee=total_fee,
            gross_profit=gross_profit,
            net_profit=gross_profit - total_fee,
        )

    def _interpret_observed_fees(self, observed_estimated_fees: float) -> str:
        if self.config.maker_fee_percent <= 0:
            return "Cannot infer observed notional because maker_fee_percent <= 0."

        implied_open_close_notional = observed_estimated_fees / self.config.maker_fee_percent
        approximate_trade_size = implied_open_close_notional / 2
        return (
            f"observed estimated_fees={observed_estimated_fees:.8f} / maker_fee={self.config.maker_fee_percent:.6f} "
            f"=> open+close notional ~= {implied_open_close_notional:.8f}, "
            f"or about {approximate_trade_size:.8f} per leg. This matches 0.1% + 0.1% on an approximately 10 USDT trade."
        )

    def _notes(self, consistency: str) -> list[str]:
        notes = [
            "No Binance account commission schedule or USDC/USDT special-fee endpoint is queried by the current code.",
            "Risk profitability estimated_fees are maker/maker in ExchangeRulesEngine.",
            "Paper execution uses taker fee for market orders.",
        ]
        if self.config.maker_fee_percent == self.config.taker_fee_percent:
            notes.append("Current maker and taker fee config values are equal, so the model mismatch is numerically hidden.")
        else:
            notes.append("Current maker and taker fee config values differ, so backtest/paper/risk profitability checks can diverge numerically.")
        return notes
