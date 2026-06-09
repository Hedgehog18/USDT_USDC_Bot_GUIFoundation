import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from config.config_manager import BotConfig


class AppLogger:
    """Єдина точка налаштування файлового логування."""

    def __init__(self, config: BotConfig) -> None:
        self.config = config

    def configure(self) -> logging.Logger:
        log_path = Path(self.config.log_file_path)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        logger = logging.getLogger("usdt_usdc_bot")
        logger.setLevel(self._level_from_config())
        logger.propagate = False

        for handler in list(logger.handlers):
            logger.removeHandler(handler)
            handler.close()

        formatter = logging.Formatter(
            "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
        )

        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=1_000_000,
            backupCount=5,
            encoding="utf-8",
        )
        file_handler.setFormatter(formatter)

        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)

        logger.addHandler(file_handler)
        logger.addHandler(console_handler)

        return logger

    def _level_from_config(self) -> int:
        level_name = self.config.log_level.upper()
        return getattr(logging, level_name, logging.INFO)
