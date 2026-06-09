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
