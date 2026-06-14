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
    assert "market_snapshots.corridor_quality_score" in applied
    assert "market_snapshots.mean_reversion_score" in applied
    assert "market_snapshots.market_health_score" in applied

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(market_snapshots)").fetchall()}

    assert "order_book_imbalance" in columns
    assert "tick_activity_score" in columns
    assert "center_crossing_score" in columns
    assert "mean_reversion_score" in columns
    assert "spread_stability_score" in columns
    assert "corridor_quality_score" in columns
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


def test_migration_backfills_legacy_paper_cycle_ids(tmp_path: Path):
    db_path = tmp_path / "bot.sqlite"

    with sqlite3.connect(db_path) as conn:
        conn.execute(
            """
            CREATE TABLE paper_cycles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                cycle_id INTEGER NOT NULL,
                direction TEXT NOT NULL,
                status TEXT NOT NULL,
                open_price REAL NOT NULL,
                close_price REAL NOT NULL,
                quantity REAL NOT NULL,
                open_fee REAL NOT NULL,
                close_fee REAL NOT NULL,
                gross_profit REAL NOT NULL,
                net_profit REAL NOT NULL,
                opened_at TEXT NOT NULL,
                closed_at TEXT
            )
            """
        )
        for direction in ("BUY_USDC", "SELL_USDC", "BUY_USDC"):
            conn.execute(
                """
                INSERT INTO paper_cycles (
                    timestamp, cycle_id, direction, status, open_price,
                    close_price, quantity, open_fee, close_fee, gross_profit,
                    net_profit, opened_at, closed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "2026-06-11T00:00:00",
                    1,
                    direction,
                    "OPEN",
                    1.0,
                    1.0002,
                    10.0,
                    0.0,
                    0.0,
                    0.0,
                    0.0,
                    "2026-06-11T00:00:00",
                    None,
                ),
            )
        conn.commit()

    manager = DatabaseMigrationManager(db_path)
    first = manager.run()
    second = manager.run()

    assert "paper_cycles.strategy_profile" in first
    assert "paper_cycles.close_reason" in first
    assert "paper_cycles.cycle_id_backfill" in first
    assert second == []
    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(paper_cycles)").fetchall()}
        rows = conn.execute(
            "SELECT id, cycle_id FROM paper_cycles ORDER BY id ASC"
        ).fetchall()

    assert "close_reason" in columns
    assert rows == [(1, 1), (2, 2), (3, 3)]
