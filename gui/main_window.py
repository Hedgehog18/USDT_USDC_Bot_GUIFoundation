from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QMainWindow, QSplitter, QTabWidget

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

        self.settings = QSettings("Hedgehog18", "USDT_USDC_Bot_GUIFoundation")
        self.config = ConfigManager().config
        self.database = DatabaseManager(self.config.database_path)

        self.setWindowTitle(f"USDT/USDC Bot MVP - v{VERSION}")
        self.resize(1000, 700)

        self.tabs = QTabWidget()
        dashboard_tab = DashboardTab(self.config, self.database)
        self.tabs.addTab(dashboard_tab, "Dashboard")
        self.tabs.addTab(HealthTab(self.config, self.database), "Health")
        self.tabs.addTab(BacktestTab(self.config, self.database), "Backtest")
        self.tabs.addTab(PaperTradingTab(self.config, self.database), "Paper Trading")
        self.tabs.addTab(AnalyticsTab(self.database), "Analytics")
        self.tabs.addTab(RunnerTab(self.config, self.database, dashboard_tab.refresh), "Runner")
        self.tabs.addTab(LogsTab(self.config.log_file_path, self.database), "Logs")
        self.tabs.addTab(SettingsTab(), "Settings")

        self.setCentralWidget(self.tabs)
        self._restore_gui_state()

    def closeEvent(self, event) -> None:
        self._save_gui_state()
        super().closeEvent(event)

    def _save_gui_state(self) -> None:
        self.settings.setValue("window/geometry", self.saveGeometry())
        self.settings.setValue("window/state", self.saveState())
        self.settings.setValue("tabs/current_index", self.tabs.currentIndex())

        for splitter in self._stateful_splitters():
            self.settings.setValue(f"splitters/{splitter.objectName()}", splitter.saveState())

    def _restore_gui_state(self) -> None:
        try:
            geometry = self.settings.value("window/geometry")
            if geometry:
                self.restoreGeometry(geometry)

            window_state = self.settings.value("window/state")
            if window_state:
                self.restoreState(window_state)

            tab_index = int(self.settings.value("tabs/current_index", 0))
            if 0 <= tab_index < self.tabs.count():
                self.tabs.setCurrentIndex(tab_index)

            for splitter in self._stateful_splitters():
                state = self.settings.value(f"splitters/{splitter.objectName()}")
                if state:
                    splitter.restoreState(state)
        except Exception:
            pass

    def _stateful_splitters(self) -> list[QSplitter]:
        return [splitter for splitter in self.findChildren(QSplitter) if splitter.objectName()]
