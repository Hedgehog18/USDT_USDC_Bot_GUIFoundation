from dataclasses import dataclass

from config.config_manager import BotConfig
from paper.models import PaperPortfolio


@dataclass(frozen=True)
class PaperSafetyResult:
    allowed: bool
    level: str
    reason: str


class PaperSafetyEngine:
    def __init__(self, config: BotConfig) -> None:
        self.config = config
        self.initial_value = config.backtest_initial_usdt + config.backtest_initial_usdc

    def check(self, portfolio: PaperPortfolio, recent_cycles: list[tuple]) -> PaperSafetyResult:
        if portfolio.total_value < self.config.paper_min_portfolio_value:
            return PaperSafetyResult(False, "CRITICAL", "Paper portfolio value нижче мінімального порогу.")

        if self.initial_value > 0:
            drawdown = (self.initial_value - portfolio.total_value) / self.initial_value
            if drawdown > self.config.paper_max_drawdown:
                return PaperSafetyResult(False, "CRITICAL", f"Paper drawdown перевищив ліміт: {drawdown:.4f}")

        closed_cycles = [row for row in recent_cycles if row[3] == "CLOSED"]
        last_cycles = closed_cycles[: self.config.paper_max_losing_cycles]

        if len(last_cycles) >= self.config.paper_max_losing_cycles:
            if all(float(row[10]) <= 0 for row in last_cycles):
                return PaperSafetyResult(
                    False,
                    "WARNING",
                    f"Останні {self.config.paper_max_losing_cycles} paper cycles збиткові.",
                )

        return PaperSafetyResult(True, "INFO", "Paper safety checks passed.")
