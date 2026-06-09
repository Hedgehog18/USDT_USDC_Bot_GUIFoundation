from dataclasses import dataclass

from backtest.models import BacktestResult, PeriodAnalytics


@dataclass(frozen=True)
class BacktestInsights:
    rating: str
    summary: str
    strengths: list[str]
    weaknesses: list[str]
    warnings: list[str]
    next_steps: list[str]


class BacktestInsightsEngine:
    """Автоматичні висновки по backtest-результату."""

    def build_insights(
        self,
        result: BacktestResult,
        periods: list[PeriodAnalytics] | None = None,
    ) -> BacktestInsights:
        periods = periods or []

        strengths: list[str] = []
        weaknesses: list[str] = []
        warnings: list[str] = []
        next_steps: list[str] = []

        if result.trades == 0:
            warnings.append("Backtest не створив жодної угоди.")
            next_steps.append("Послабити фільтри DecisionEngine або перевірити target_profit.")
            return BacktestInsights(
                rating="NO_TRADES",
                summary="Стратегія не дала торгових входів на цьому відрізку.",
                strengths=strengths,
                weaknesses=["Немає статистично значущих угод."],
                warnings=warnings,
                next_steps=next_steps,
            )

        if result.net_profit > 0:
            strengths.append("Net profit позитивний.")
        else:
            weaknesses.append("Net profit негативний або нульовий.")

        if result.win_rate >= 0.60:
            strengths.append("Win rate вище 60%.")
        elif result.win_rate < 0.45:
            weaknesses.append("Win rate нижче 45%.")

        if result.profit_factor >= 1.5:
            strengths.append("Profit Factor вище 1.5.")
        elif result.profit_factor < 1.0:
            weaknesses.append("Profit Factor нижче 1.0.")

        if result.max_drawdown <= 0.02:
            strengths.append("Max drawdown нижче 2%.")
        elif result.max_drawdown > 0.05:
            warnings.append("Max drawdown вище 5%.")

        if result.sharpe_ratio > 0.5:
            strengths.append("Sharpe Ratio позитивний.")
        elif result.sharpe_ratio < 0:
            weaknesses.append("Sharpe Ratio негативний.")

        if periods:
            profitable_periods = sum(1 for item in periods if item.profit > 0)
            if profitable_periods == len(periods):
                strengths.append("Усі періоди прибуткові.")
            elif profitable_periods < len(periods) / 2:
                weaknesses.append("Менше половини періодів прибуткові.")

        rating = self._rating(result, weaknesses, warnings)

        if rating in {"GOOD", "PROMISING"}:
            next_steps.append("Запустити walk-forward на більшому періоді.")
            next_steps.append("Порівняти кілька target_profit/trade_size_percent через parameter-sweep.")
        else:
            next_steps.append("Переглянути фільтри входу та risk settings.")
            next_steps.append("Перевірити інші інтервали candles.")

        return BacktestInsights(
            rating=rating,
            summary=self._summary_for_rating(rating),
            strengths=strengths,
            weaknesses=weaknesses,
            warnings=warnings,
            next_steps=next_steps,
        )

    @staticmethod
    def _rating(result: BacktestResult, weaknesses: list[str], warnings: list[str]) -> str:
        if result.net_profit <= 0:
            return "WEAK"

        if result.roi > 0.01 and result.profit_factor >= 1.5 and result.max_drawdown <= 0.03:
            return "GOOD"

        if result.roi > 0 and len(warnings) == 0 and len(weaknesses) <= 1:
            return "PROMISING"

        return "MIXED"

    @staticmethod
    def _summary_for_rating(rating: str) -> str:
        summaries = {
            "GOOD": "Backtest виглядає сильним, але потребує walk-forward перевірки.",
            "PROMISING": "Backtest перспективний, але ще не достатній для Paper Trading.",
            "MIXED": "Backtest змішаний: є позитив, але ризики або слабкі місця суттєві.",
            "WEAK": "Backtest слабкий: стратегія потребує доопрацювання.",
            "NO_TRADES": "Немає угод для оцінки стратегії.",
        }
        return summaries.get(rating, "Невідомий результат.")
