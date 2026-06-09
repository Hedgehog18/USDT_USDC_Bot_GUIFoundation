from dataclasses import dataclass

from paper.paper_analytics_engine import PaperAnalytics


@dataclass(frozen=True)
class PaperInsights:
    rating: str
    summary: str
    strengths: list[str]
    weaknesses: list[str]
    warnings: list[str]
    next_steps: list[str]


class PaperInsightsEngine:
    def build(self, stats: PaperAnalytics, safety_events: list[tuple]) -> PaperInsights:
        if stats.closed_cycles == 0:
            return PaperInsights(
                rating="NO_CLOSED_CYCLES",
                summary="Paper режим ще не має закритих циклів для оцінки.",
                strengths=[],
                weaknesses=["Немає закритих paper cycles."],
                warnings=[],
                next_steps=["Запустити paper-cycle-sim на більшій кількості ітерацій."],
            )

        strengths = []
        weaknesses = []
        warnings = []
        next_steps = []

        blocked = [row for row in safety_events if int(row[2]) == 0]

        if stats.net_profit > 0:
            strengths.append("Paper net profit позитивний.")
        else:
            weaknesses.append("Paper net profit не позитивний.")

        if stats.win_rate >= 0.60:
            strengths.append("Paper win rate вище 60%.")
        elif stats.win_rate < 0.45:
            weaknesses.append("Paper win rate нижче 45%.")

        if stats.profit_factor >= 1.5:
            strengths.append("Paper profit factor вище 1.5.")
        elif stats.profit_factor < 1.0:
            weaknesses.append("Paper profit factor нижче 1.0.")

        if blocked:
            warnings.append(f"Було {len(blocked)} paper safety stop/event.")

        if stats.closed_cycles < 20:
            warnings.append("Мало закритих paper cycles для статистичної оцінки.")

        rating = self._rating(stats, blocked, weaknesses)

        if rating in {"GOOD", "PROMISING"}:
            next_steps.append("Запустити довший paper-run на реальних market data.")
            next_steps.append("Порівняти paper stats з backtest/walk-forward.")
        else:
            next_steps.append("Перевірити DecisionEngine/RiskManager фільтри.")
            next_steps.append("Переглянути paper safety thresholds.")

        return PaperInsights(
            rating=rating,
            summary=self._summary(rating),
            strengths=strengths,
            weaknesses=weaknesses,
            warnings=warnings,
            next_steps=next_steps,
        )

    @staticmethod
    def _rating(stats: PaperAnalytics, blocked_events: list[tuple], weaknesses: list[str]) -> str:
        if stats.closed_cycles == 0:
            return "NO_CLOSED_CYCLES"
        if stats.net_profit <= 0:
            return "WEAK"
        if not blocked_events and stats.win_rate >= 0.60 and stats.profit_factor >= 1.5:
            return "GOOD"
        if stats.net_profit > 0 and len(weaknesses) <= 1:
            return "PROMISING"
        return "MIXED"

    @staticmethod
    def _summary(rating: str) -> str:
        return {
            "GOOD": "Paper trading виглядає сильним, але ще потребує довшої перевірки.",
            "PROMISING": "Paper trading перспективний, але є що перевірити.",
            "MIXED": "Paper trading змішаний: є позитив і помітні слабкі місця.",
            "WEAK": "Paper trading слабкий: перед real trading переходити рано.",
            "NO_CLOSED_CYCLES": "Недостатньо закритих циклів для висновків.",
        }.get(rating, "Невідомий результат.")
