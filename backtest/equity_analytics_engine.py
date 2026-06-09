from backtest.models import BacktestTrade, EquityPoint, PeriodAnalytics


class EquityAnalyticsEngine:
    """Аналітика equity curve.

    MVP-версія працює по індексах candles, а не по календарних місяцях.
    period_size задає розмір умовного періоду у candles.
    """

    def build_equity_points(self, equity_curve: list[float]) -> list[EquityPoint]:
        return [
            EquityPoint(index=index, value=value)
            for index, value in enumerate(equity_curve)
        ]

    def build_period_analytics(
        self,
        equity_curve: list[float],
        trades: list[BacktestTrade],
        period_size: int = 100,
    ) -> list[PeriodAnalytics]:
        if period_size <= 0:
            raise ValueError("period_size має бути більшим за 0.")

        if not equity_curve:
            return []

        periods: list[PeriodAnalytics] = []
        start = 0
        period_number = 1

        while start < len(equity_curve) - 1:
            end = min(start + period_size, len(equity_curve) - 1)

            start_value = equity_curve[start]
            end_value = equity_curve[end]
            profit = end_value - start_value
            roi = (profit / start_value) if start_value > 0 else 0.0

            period_trades = [
                trade for trade in trades
                if start <= trade.index <= end
            ]

            periods.append(
                PeriodAnalytics(
                    period=f"period_{period_number}",
                    start_value=start_value,
                    end_value=end_value,
                    profit=profit,
                    roi=roi,
                    trades=len(period_trades),
                )
            )

            start += period_size
            period_number += 1

        return periods
