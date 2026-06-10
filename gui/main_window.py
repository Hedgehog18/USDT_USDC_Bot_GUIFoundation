from PySide6.QtCore import QSettings, QSize
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMainWindow, QMessageBox, QSplitter, QTabWidget

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
        self.setMinimumSize(QSize(1280, 820))
        self.resize(1500, 920)

        self._create_actions()
        self._create_menus()
        self.statusBar().showMessage("Ready")

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(False)
        self.tabs.setStyleSheet(
            """
            QTabWidget::pane {
                border-top: 1px solid #4b5563;
            }
            QTabBar::tab {
                background: #2f2f2f;
                border: 1px solid #444;
                border-bottom: none;
                color: #f3f4f6;
                min-width: 84px;
                padding: 8px 14px;
                margin-right: 2px;
                font-weight: 600;
            }
            QTabBar::tab:selected {
                background: #3f4652;
                color: #ffffff;
                border-color: #6b7280;
                border-top: 2px solid #60a5fa;
            }
            QTabBar::tab:hover:!selected {
                background: #3a3a3a;
                border-top: 2px solid #9ca3af;
            }
            """
        )
        dashboard_tab = DashboardTab(self.config, self.database)
        self.tabs.addTab(dashboard_tab, "Dashboard")
        self.tabs.addTab(HealthTab(self.config, self.database), "Health")
        self.tabs.addTab(BacktestTab(self.config, self.database), "Backtest")
        self.tabs.addTab(PaperTradingTab(self.config, self.database), "Paper Trading")
        self.tabs.addTab(AnalyticsTab(self.database, self.config), "Analytics")
        self.tabs.addTab(RunnerTab(self.config, self.database, dashboard_tab.refresh), "Runner")
        self.tabs.addTab(LogsTab(self.config.log_file_path, self.database), "Logs")
        self.tabs.addTab(SettingsTab(), "Settings")

        self.setCentralWidget(self.tabs)
        self._restore_gui_state()
        self._ensure_usable_window_size()

    def refresh_current_tab(self) -> None:
        current_widget = self.tabs.currentWidget()
        current_title = self.tabs.tabText(self.tabs.currentIndex())
        refresh_method = getattr(current_widget, "refresh", None)

        if callable(refresh_method):
            try:
                refresh_method()
            except Exception as exc:
                self.statusBar().showMessage(f"Refresh failed: {exc}", 5000)
                return
            self.statusBar().showMessage(f"Refreshed {current_title}", 3000)
            return

        self.statusBar().showMessage(f"{current_title} has no refresh action", 3000)

    def show_about_dialog(self) -> None:
        QMessageBox.about(
            self,
            "About USDT/USDC Bot MVP",
            "\n".join([
                "USDT/USDC Bot MVP",
                f"Version: {VERSION}",
                "Mode: Demo/Paper only",
                "Real trading disabled",
            ]),
        )

    def closeEvent(self, event) -> None:
        self._save_gui_state()
        super().closeEvent(event)

    def _create_actions(self) -> None:
        self.exit_action = QAction("Exit", self)
        self.exit_action.setShortcut("Ctrl+Q")
        self.exit_action.setStatusTip("Close the GUI")
        self.exit_action.triggered.connect(self.close)

        self.refresh_current_tab_action = QAction("Refresh Current Tab", self)
        self.refresh_current_tab_action.setShortcut("F5")
        self.refresh_current_tab_action.setStatusTip("Refresh the active tab")
        self.refresh_current_tab_action.triggered.connect(self.refresh_current_tab)

        self.about_action = QAction("About", self)
        self.about_action.setStatusTip("Show application information")
        self.about_action.triggered.connect(self.show_about_dialog)

    def _create_menus(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction(self.exit_action)

        view_menu = self.menuBar().addMenu("View")
        view_menu.addAction(self.refresh_current_tab_action)

        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction(self.about_action)

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

    def _ensure_usable_window_size(self) -> None:
        current_size = self.size()
        width = max(current_size.width(), 1280)
        height = max(current_size.height(), 820)
        if width != current_size.width() or height != current_size.height():
            self.resize(width, height)

    def _stateful_splitters(self) -> list[QSplitter]:
        return [splitter for splitter in self.findChildren(QSplitter) if splitter.objectName()]
