from datetime import datetime
import json

from app.bot_engine import BotEngine
from config.config_manager import ConfigManager
from market.models import MarketState
from runner.bot_runner import BotRunner


class FakeBot:
    def __init__(self):
        self.calls = 0

    def start(self):
        self.calls += 1


def test_runner_runs_limited_iterations():
    bot = FakeBot()
    runner = BotRunner(
        bot=bot,
        interval_seconds=1,
        max_iterations=2,
    )

    result = runner.run()

    assert bot.calls == 2
    assert result.iterations_completed == 2
    assert result.stopped_by_limit is True


def test_runner_stop_request_before_run():
    bot = FakeBot()
    runner = BotRunner(
        bot=bot,
        interval_seconds=1,
        max_iterations=2,
    )
    runner.request_stop()

    result = runner.run()

    assert bot.calls == 0
    assert result.iterations_completed == 0
    assert result.stopped_by_limit is False


class FakeMarketAnalyzer:
    def analyze_market(self):
        return MarketState(
            symbol="USDCUSDT",
            price=1.0,
            bid=0.99999,
            ask=1.00001,
            spread=0.00002,
            work_low=0.9999,
            work_high=1.0001,
            work_center=1.0,
            work_position=50.0,
            short_low=0.9998,
            short_high=1.0002,
            short_center=1.0,
            short_position=50.0,
            long_low=0.9995,
            long_high=1.0005,
            long_center=1.0,
            long_position=50.0,
            center_confidence="HIGH",
            center_alignment="FLAT",
            tick_activity_score=80.0,
            center_crossing_score=80.0,
            mean_reversion_score=80.0,
            spread_stability_score=90.0,
            corridor_quality_score=80.0,
            market_activity_score=80.0,
            market_regime="NORMAL",
            order_book_imbalance=0.0,
            order_book_pressure="BALANCED",
            trade_volume_delta=0.0,
            micro_trend="NEUTRAL",
            relative_volatility=0.00001,
            volatility_regime="LOW",
            market_health_score=100.0,
            market_health_status="HEALTHY",
            market_health_reason="test",
            created_at=datetime.utcnow(),
        )


class PassingHealthCheck:
    def run(self):
        class Report:
            ok = True
            failed_items = []

        return Report()


def test_demo_runner_runs_bot_engine_iteration_without_portfolio_stats_error(tmp_path, monkeypatch):
    settings = json.loads(ConfigManager.DEFAULT_PATH.read_text(encoding="utf-8"))
    settings["database_path"] = str(tmp_path / "bot.sqlite")
    settings["use_real_market_data"] = False
    settings_path = tmp_path / "settings.json"
    settings_path.write_text(json.dumps(settings), encoding="utf-8")
    monkeypatch.setattr(ConfigManager, "DEFAULT_PATH", settings_path)

    bot = BotEngine()
    bot.market_analyzer = FakeMarketAnalyzer()
    bot.health_check = PassingHealthCheck()
    runner = BotRunner(bot=bot, interval_seconds=1, max_iterations=1)

    result = runner.run()

    assert result.iterations_completed == 1
    assert bot.database.count_rows("trade_signals") == 1
