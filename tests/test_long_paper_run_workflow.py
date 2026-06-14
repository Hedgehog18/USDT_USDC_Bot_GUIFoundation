from paper.long_paper_run_workflow import LongPaperRunWorkflow
from paper.models import PaperPortfolio
from paper.paper_trading_engine import PaperTradingRunResult
from storage.database_manager import DatabaseManager


class DummyConfig:
    backtest_initial_usdt = 50.0
    backtest_initial_usdc = 50.0
    buy_zone_max = 20.0
    sell_zone_min = 80.0


class FakePaperTradingEngine:
    def __init__(self, config, database, strategy_profile="strict_current", **kwargs):
        self.config = config
        self.database = database
        self.strategy_profile = strategy_profile
        self.kwargs = kwargs

    def run(self, iterations: int) -> PaperTradingRunResult:
        return PaperTradingRunResult(
            iterations=iterations,
            opened_cycles=0,
            closed_cycles=0,
            safety_stops=0,
            final_portfolio=PaperPortfolio(usdt=50.0, usdc=50.0),
        )


def test_long_paper_run_workflow_saves_history(monkeypatch, tmp_path):
    import paper.long_paper_run_workflow as workflow_module

    monkeypatch.setattr(workflow_module, "PaperTradingEngine", FakePaperTradingEngine)
    monkeypatch.chdir(tmp_path)
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    result = LongPaperRunWorkflow(DummyConfig(), database).run(iterations=2, interval_seconds=0)

    rows = database.load_recent_long_paper_runs(limit=10)
    assert result.long_run_id == 1
    assert result.run_id == 1
    assert len(rows) == 1
    assert rows[0][2] == 2
    assert rows[0][3] == 0
    assert rows[0][4] == 100.0
    assert rows[0][8] == result.validation_summary.overall_status
    assert rows[0][9] == result.insights.rating
    assert result.strategy_profile == "strict_current"


def test_long_paper_run_workflow_uses_profile_aware_summary(monkeypatch, tmp_path):
    import paper.long_paper_run_workflow as workflow_module

    class FakeBotEngine:
        def __init__(self):
            self.config = DummyConfig()
            self.decision_engine = None

    class FakeProfileDecisionEngine:
        def __init__(self, config, strategy_profile):
            self.config = config
            self.strategy_profile = strategy_profile

    monkeypatch.setattr(workflow_module, "PaperTradingEngine", FakePaperTradingEngine)
    monkeypatch.setattr(workflow_module, "BotEngine", FakeBotEngine)
    monkeypatch.setattr(workflow_module, "StrategyProfileDecisionEngine", FakeProfileDecisionEngine)
    monkeypatch.chdir(tmp_path)
    database = DatabaseManager(str(tmp_path / "bot.sqlite"))

    result = LongPaperRunWorkflow(DummyConfig(), database).run(
        iterations=2,
        interval_seconds=0,
        strategy_profile="mean_reversion_v2_small_target_ny",
    )

    rows = database.load_recent_long_paper_runs(limit=10)
    assert result.strategy_profile == "mean_reversion_v2_small_target_ny"
    assert result.validation_summary.profile == "mean_reversion_v2_small_target_ny"
    assert rows[0][8] == result.validation_summary.overall_status
