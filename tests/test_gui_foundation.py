def test_gui_main_window_imports():
    from gui.main_window import MainWindow

    assert MainWindow is not None


def test_paper_trading_tab_imports():
    from gui.main_window import PaperTradingTab

    assert PaperTradingTab is not None
