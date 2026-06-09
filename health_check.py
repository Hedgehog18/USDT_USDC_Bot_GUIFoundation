from app.app_logger import AppLogger
from config.config_manager import ConfigManager
from health.health_check import HealthCheck


def main() -> None:
    config = ConfigManager().config
    logger = AppLogger(config).configure()
    report = HealthCheck(config=config).run()
    logger.info("Health check executed: ok=%s", report.ok)

    print("=== Health Check ===")
    for item in report.items:
        status = "OK" if item.ok else "FAIL"
        print(f"[{status}] {item.name}: {item.message}")

    if report.ok:
        print("Система готова до Demo-запуску.")
    else:
        print("Є проблеми, які потрібно виправити перед запуском.")


if __name__ == "__main__":
    main()
