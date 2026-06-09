import sqlite3
from pathlib import Path

from storage.database_migration_manager import DatabaseMigrationManager


def test_migration_adds_missing_market_snapshot_columns(tmp_path: Path):
    db_path = tmp_path / "bot.sqlite"

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE market_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                price REAL NOT NULL,
                bid REAL NOT NULL,
                ask REAL NOT NULL,
                spread REAL NOT NULL,
                work_center REAL NOT NULL,
                work_position REAL NOT NULL,
                short_center REAL NOT NULL,
                short_position REAL NOT NULL,
                long_center REAL NOT NULL,
                long_position REAL NOT NULL,
                center_confidence TEXT NOT NULL,
                center_alignment TEXT NOT NULL,
                market_activity_score REAL NOT NULL,
                market_regime TEXT NOT NULL
            )
            """
        )
        conn.commit()

    manager = DatabaseMigrationManager(db_path)
    applied = manager.run()

    assert "market_snapshots.order_book_imbalance" in applied
    assert "market_snapshots.market_health_score" in applied

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(market_snapshots)").fetchall()}

    assert "order_book_imbalance" in columns
    assert "market_health_status" in columns


def test_migration_is_idempotent(tmp_path: Path):
    db_path = tmp_path / "bot.sqlite"

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE market_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                symbol TEXT NOT NULL,
                price REAL NOT NULL,
                bid REAL NOT NULL,
                ask REAL NOT NULL,
                spread REAL NOT NULL,
                work_center REAL NOT NULL,
                work_position REAL NOT NULL,
                short_center REAL NOT NULL,
                short_position REAL NOT NULL,
                long_center REAL NOT NULL,
                long_position REAL NOT NULL,
                center_confidence TEXT NOT NULL,
                center_alignment TEXT NOT NULL,
                market_activity_score REAL NOT NULL,
                market_regime TEXT NOT NULL
            )
            """
        )
        conn.commit()

    manager = DatabaseMigrationManager(db_path)

    first = manager.run()
    second = manager.run()

    assert first
    assert second == []
