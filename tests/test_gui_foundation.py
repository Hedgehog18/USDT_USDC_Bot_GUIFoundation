def test_gui_main_window_imports():
    from gui.main_window import MainWindow

    assert MainWindow is not None


def test_dashboard_tab_imports():
    from gui.main_window import DashboardTab

    assert DashboardTab is not None


def test_paper_trading_tab_imports():
    from gui.main_window import PaperTradingTab

    assert PaperTradingTab is not None


def test_backtest_tab_imports():
    from gui.main_window import BacktestTab

    assert BacktestTab is not None


def test_logs_tab_imports():
    from gui.main_window import LogsTab

    assert LogsTab is not None
