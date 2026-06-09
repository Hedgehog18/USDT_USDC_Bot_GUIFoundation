from app.app_logger import AppLogger
from app.bot_engine import BotEngine
from config.config_manager import ConfigManager
from runner.bot_runner import BotRunner


def main() -> None:
    config = ConfigManager().config
    logger = AppLogger(config).configure()
    logger.info("Application started")
    bot = BotEngine()
    runner = BotRunner(
        bot=bot,
        interval_seconds=config.runner_interval_seconds,
        max_iterations=config.max_runner_iterations,
    )
    result = runner.run()

    logger.info("Runner finished: iterations=%s stopped_by_limit=%s", result.iterations_completed, result.stopped_by_limit)
    print(
        f"Runner завершено. Ітерацій: {result.iterations_completed}. "
        f"Зупинено по ліміту: {result.stopped_by_limit}"
    )


if __name__ == "__main__":
    main()
