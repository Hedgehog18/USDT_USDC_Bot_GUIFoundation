from config.config_manager import ConfigManager
from storage.database_manager import DatabaseManager


def main() -> None:
    config = ConfigManager().config
    database = DatabaseManager(config.database_path)
    applied = database.run_migrations()

    if applied:
        print("Застосовано міграції:")
        for item in applied:
            print(f"- {item}")
    else:
        print("Міграції не потрібні. База вже актуальна.")


if __name__ == "__main__":
    main()
