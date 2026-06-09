from dataclasses import replace
from pathlib import Path

from app.app_logger import AppLogger


def test_app_logger_creates_log_file(test_config, tmp_path: Path):
    config = replace(
        test_config,
        log_file_path=str(tmp_path / "bot.log"),
        log_level="INFO",
    )

    logger = AppLogger(config).configure()
    logger.info("test message")

    assert (tmp_path / "bot.log").exists()


def test_app_logger_handles_unknown_level(test_config, tmp_path: Path):
    config = replace(
        test_config,
        log_file_path=str(tmp_path / "bot.log"),
        log_level="UNKNOWN",
    )

    logger = AppLogger(config).configure()
    logger.info("test message")

    assert (tmp_path / "bot.log").exists()
