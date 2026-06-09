from PySide6.QtWidgets import QMainWindow, QTabWidget

from app.version import VERSION
from config.config_manager import ConfigManager
from gui.analytics_tab import AnalyticsTab
from gui.backtest_tab import BacktestTab
from gui.dashboard_tab import DashboardTab
from gui.health_tab import HealthTab
from gui.logs_tab import LogsTab
from gui.paper_trading_tab import PaperTradingTab
from gui.runner_tab import RunnerTab
from gui.settings_tab import SettingsTab
from storage.database_manager import DatabaseManager


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.config = ConfigManager().config
        self.database = DatabaseManager(self.config.database_path)

        self.setWindowTitle(f"USDT/USDC Bot MVP - v{VERSION}")
        self.resize(1000, 700)

        tabs = QTabWidget()
        dashboard_tab = DashboardTab(self.config, self.database)
        tabs.addTab(dashboard_tab, "Dashboard")
        tabs.addTab(HealthTab(self.config, self.database), "Health")
        tabs.addTab(BacktestTab(self.config, self.database), "Backtest")
        tabs.addTab(PaperTradingTab(self.config, self.database), "Paper Trading")
        tabs.addTab(AnalyticsTab(self.database), "Analytics")
        tabs.addTab(RunnerTab(self.config, self.database, dashboard_tab.refresh), "Runner")
        tabs.addTab(LogsTab(self.config.log_file_path, self.database), "Logs")
        tabs.addTab(SettingsTab(), "Settings")

        self.setCentralWidget(tabs)
