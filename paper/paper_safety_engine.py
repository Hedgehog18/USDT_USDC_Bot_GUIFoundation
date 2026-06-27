from dataclasses import dataclass

from config.config_manager import BotConfig
from paper.models import PaperPortfolio


HF_SAFETY_PROFILE = "mean_reversion_hf_micro_v1"
HF_MAX_CONSECUTIVE_LOSSES = 10
HF_MAX_REALIZED_DRAWDOWN = -0.005
HF_TIMEOUT_LOSS_RATE_LIMIT = 0.80
HF_TIMEOUT_WINDOW = 30
HF_SAFETY_MIN_CYCLES = 30


@dataclass(frozen=True)
class PaperSafetyResult:
    allowed: bool
    level: str
    reason: str
    diagnostics: dict[str, str] | None = None


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

    def check_for_profile(
        self,
        portfolio: PaperPortfolio,
        recent_cycles: list[tuple],
        *,
        strategy_profile: str,
        baseline_max_id: int = 0,
    ) -> PaperSafetyResult:
        if strategy_profile != HF_SAFETY_PROFILE:
            result = self.check(portfolio, recent_cycles)
            return PaperSafetyResult(
                result.allowed,
                result.level,
                result.reason,
                self._classic_diagnostics(),
            )

        return self._check_hf_micro(
            portfolio,
            recent_cycles,
            baseline_max_id=baseline_max_id,
        )

    def _check_hf_micro(
        self,
        portfolio: PaperPortfolio,
        recent_cycles: list[tuple],
        *,
        baseline_max_id: int,
    ) -> PaperSafetyResult:
        diagnostics = self._hf_diagnostics(recent_cycles, baseline_max_id)

        if portfolio.total_value < self.config.paper_min_portfolio_value:
            return PaperSafetyResult(
                False,
                "CRITICAL",
                "Paper portfolio value below minimum threshold.",
                diagnostics,
            )

        if self.initial_value > 0:
            drawdown = (self.initial_value - portfolio.total_value) / self.initial_value
            if drawdown > self.config.paper_max_drawdown:
                return PaperSafetyResult(
                    False,
                    "CRITICAL",
                    f"Paper drawdown exceeded limit: {drawdown:.4f}",
                    diagnostics,
                )

        closed_count = int(diagnostics["safety_window_cycles"])
        if closed_count < HF_SAFETY_MIN_CYCLES:
            return PaperSafetyResult(
                True,
                "INFO",
                "HF paper safety checks passed: minimum sample window not reached.",
                diagnostics,
            )

        consecutive_losses = int(diagnostics["safety_consecutive_losses"].split("/")[0].strip())
        if consecutive_losses >= HF_MAX_CONSECUTIVE_LOSSES:
            return PaperSafetyResult(
                False,
                "WARNING",
                f"HF max consecutive losses reached: {consecutive_losses}/{HF_MAX_CONSECUTIVE_LOSSES}.",
                diagnostics,
            )

        realized_drawdown = float(diagnostics["safety_realized_drawdown"].split("/")[0].strip())
        if realized_drawdown <= HF_MAX_REALIZED_DRAWDOWN:
            return PaperSafetyResult(
                False,
                "WARNING",
                f"HF realized drawdown limit reached: {realized_drawdown:.8f} <= {HF_MAX_REALIZED_DRAWDOWN:.8f}.",
                diagnostics,
            )

        timeout_loss_rate = float(diagnostics["safety_timeout_loss_rate"].rstrip("%")) / 100.0
        timeout_window_net = float(diagnostics["safety_timeout_window_net"])
        if timeout_loss_rate >= HF_TIMEOUT_LOSS_RATE_LIMIT and timeout_window_net < 0:
            return PaperSafetyResult(
                False,
                "WARNING",
                f"HF timeout loss rate limit reached: {timeout_loss_rate * 100:.2f}%.",
                diagnostics,
            )

        return PaperSafetyResult(True, "INFO", "HF paper safety checks passed.", diagnostics)

    @staticmethod
    def _classic_diagnostics() -> dict[str, str]:
        return {
            "paper_safety_policy": "classic",
            "safety_window_scope": "full_history",
            "safety_window_cycles": "N/A",
            "safety_consecutive_losses": "N/A",
            "safety_realized_drawdown": "N/A",
            "safety_timeout_loss_rate": "N/A",
            "safety_timeout_window_net": "N/A",
            "safety_min_cycles_met": "N/A",
        }

    def _hf_diagnostics(self, recent_cycles: list[tuple], baseline_max_id: int) -> dict[str, str]:
        closed_cycles = [row for row in recent_cycles if self._status(row) in {"CLOSED", "CLOSED_MANUAL"}]
        consecutive_losses = 0
        for row in closed_cycles:
            if self._net_profit(row) < 0:
                consecutive_losses += 1
            else:
                break

        net_profit = sum(self._net_profit(row) for row in closed_cycles)
        timeout_window = closed_cycles[:HF_TIMEOUT_WINDOW]
        timeout_losses = [
            row
            for row in timeout_window
            if self._close_reason(row).startswith("max_holding_") and self._net_profit(row) < 0
        ]
        timeout_loss_rate = (len(timeout_losses) / len(timeout_window)) if timeout_window else 0.0
        timeout_window_net = sum(self._net_profit(row) for row in timeout_window)

        return {
            "paper_safety_policy": "hf_micro",
            "safety_window_scope": "new_run" if baseline_max_id > 0 else "full_profile_history",
            "safety_window_cycles": str(len(closed_cycles)),
            "safety_consecutive_losses": f"{consecutive_losses} / {HF_MAX_CONSECUTIVE_LOSSES}",
            "safety_realized_drawdown": f"{net_profit:.8f} / {HF_MAX_REALIZED_DRAWDOWN:.8f}",
            "safety_timeout_loss_rate": f"{timeout_loss_rate * 100:.2f}%",
            "safety_timeout_window_net": f"{timeout_window_net:.8f}",
            "safety_min_cycles_met": "yes" if len(closed_cycles) >= HF_SAFETY_MIN_CYCLES else "no",
        }

    @staticmethod
    def _status(row: tuple) -> str:
        return str(row[3])

    @staticmethod
    def _net_profit(row: tuple) -> float:
        return float(row[10])

    @staticmethod
    def _close_reason(row: tuple) -> str:
        return str(row[11]) if len(row) > 11 and row[11] is not None else ""
