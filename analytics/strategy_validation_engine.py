from dataclasses import dataclass

from storage.database_manager import DatabaseManager


CONFIDENCE_SCORES = {
    "NONE": 0.0,
    "UNKNOWN": 0.0,
    "LOW": 0.25,
    "MEDIUM": 0.5,
    "NORMAL": 0.5,
    "HIGH": 0.75,
    "VERY_HIGH": 1.0,
}


@dataclass(frozen=True)
class StrategyValidationSummary:
    total_signals: int
    buy_signals: int
    sell_signals: int
    average_confidence: float
    average_spread: float
    average_volatility: float
    market_regime_distribution: dict[str, int]


class StrategyValidationEngine:
    def __init__(self, database: DatabaseManager) -> None:
        self.database = database

    def build_summary(self) -> StrategyValidationSummary:
        signal_rows = self._load_signal_rows()
        total_signals = len(signal_rows)
        buy_signals = sum(1 for action, _confidence in signal_rows if str(action).upper().startswith("BUY"))
        sell_signals = sum(1 for action, _confidence in signal_rows if str(action).upper().startswith("SELL"))

        confidence_sum = sum(self._confidence_to_score(confidence) for _action, confidence in signal_rows)
        average_confidence = confidence_sum / total_signals if total_signals else 0.0

        average_spread, average_volatility = self._load_market_averages()

        return StrategyValidationSummary(
            total_signals=total_signals,
            buy_signals=buy_signals,
            sell_signals=sell_signals,
            average_confidence=average_confidence,
            average_spread=average_spread,
            average_volatility=average_volatility,
            market_regime_distribution=self._load_market_regime_distribution(),
        )

    def _load_signal_rows(self) -> list[tuple[str, str]]:
        with self.database.connect() as conn:
            return conn.execute(
                """
                SELECT action, confidence
                FROM trade_signals
                ORDER BY timestamp ASC
                """
            ).fetchall()

    def _load_market_averages(self) -> tuple[float, float]:
        with self.database.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COALESCE(AVG(spread), 0),
                    COALESCE(AVG(relative_volatility), 0)
                FROM market_snapshots
                """
            ).fetchone()
            return float(row[0]), float(row[1])

    def _load_market_regime_distribution(self) -> dict[str, int]:
        with self.database.connect() as conn:
            rows = conn.execute(
                """
                SELECT market_regime, COUNT(*)
                FROM market_snapshots
                GROUP BY market_regime
                ORDER BY COUNT(*) DESC, market_regime ASC
                """
            ).fetchall()
            return {str(regime): int(count) for regime, count in rows}

    @staticmethod
    def _confidence_to_score(confidence: str) -> float:
        raw_value = str(confidence).strip()
        if not raw_value:
            return 0.0

        try:
            return float(raw_value)
        except ValueError:
            pass

        normalized = raw_value.upper().replace(" ", "_").replace("-", "_")
        return CONFIDENCE_SCORES.get(normalized, 0.0)
