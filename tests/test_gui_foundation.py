def test_gui_main_window_imports():
    from gui.main_window import MainWindow

    assert MainWindow is not None


def test_gui_main_window_menu_methods_exist():
    from gui.main_window import MainWindow

    assert hasattr(MainWindow, "refresh_current_tab")
    assert hasattr(MainWindow, "show_about_dialog")


def test_dashboard_tab_imports():
    from gui.main_window import DashboardTab

    assert DashboardTab is not None


def test_paper_trading_tab_imports():
    from gui.main_window import PaperTradingTab

    assert PaperTradingTab is not None


def test_paper_trading_tab_long_run_controls_import():
    from gui.paper_trading_tab import LongPaperRunWorker, PaperTradingTab

    assert LongPaperRunWorker is not None
    assert hasattr(PaperTradingTab, "start_long_paper_run")


def test_backtest_tab_imports():
    from gui.main_window import BacktestTab

    assert BacktestTab is not None


def test_logs_tab_imports():
    from gui.main_window import LogsTab

    assert LogsTab is not None


def test_settings_tab_imports():
    from gui.main_window import SettingsTab

    assert SettingsTab is not None


def test_analytics_tab_imports():
    from gui.analytics_tab import AnalyticsTab
    from gui.main_window import AnalyticsTab as MainWindowAnalyticsTab

    assert AnalyticsTab is not None
    assert MainWindowAnalyticsTab is AnalyticsTab


def test_runner_tab_imports():
    from gui.main_window import RunnerTab as MainWindowRunnerTab
    from gui.runner_tab import RunnerTab

    assert RunnerTab is not None
    assert MainWindowRunnerTab is RunnerTab


def test_runner_tab_repairs_mojibake_text():
    from gui.runner_tab import clean_display_text

    assert clean_display_text("Р¦С–РЅР°") == "Ціна"


def test_runner_status_guards():
    from gui.runner_tab import RunnerStatus, can_start_runner, can_stop_runner

    assert can_start_runner(RunnerStatus.IDLE, "DEMO") == (True, "")
    assert can_start_runner(RunnerStatus.RUNNING, "DEMO")[0] is False
    assert can_start_runner(RunnerStatus.IDLE, "REAL")[0] is False
    assert can_stop_runner(RunnerStatus.RUNNING) == (True, "")
    assert can_stop_runner(RunnerStatus.IDLE)[0] is False


def test_gui_tab_modules_import():
    from gui.analytics_tab import AnalyticsTab
    from gui.backtest_tab import BacktestTab
    from gui.dashboard_tab import DashboardTab
    from gui.health_tab import HealthTab
    from gui.logs_tab import LogsTab
    from gui.paper_trading_tab import PaperTradingTab
    from gui.runner_tab import RunnerTab
    from gui.settings_tab import SettingsTab

    assert AnalyticsTab is not None
    assert BacktestTab is not None
    assert DashboardTab is not None
    assert HealthTab is not None
    assert LogsTab is not None
    assert PaperTradingTab is not None
    assert RunnerTab is not None
    assert SettingsTab is not None
