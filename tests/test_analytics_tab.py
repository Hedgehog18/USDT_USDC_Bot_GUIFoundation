from gui.analytics_tab import calculate_drawdown_curve


def test_calculate_drawdown_curve():
    drawdowns = calculate_drawdown_curve([100.0, 110.0, 99.0, 121.0, 115.0])

    assert drawdowns == [0.0, 0.0, -0.1, 0.0, -6.0 / 121.0]
