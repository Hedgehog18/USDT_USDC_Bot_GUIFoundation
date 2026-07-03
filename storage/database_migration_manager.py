import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ColumnDefinition:
    name: str
    definition: str


class DatabaseMigrationManager:
    """Легкі SQLite-міграції для MVP.

    Для нашого поточного етапу достатньо:
    - перевірити, які колонки вже є;
    - додати відсутні через ALTER TABLE;
    - не ламати існуючу БД при оновленні проєкту.
    """

    REQUIRED_COLUMNS: dict[str, list[ColumnDefinition]] = {
        "backtest_runs": [
            ColumnDefinition("sharpe_ratio", "REAL DEFAULT 0"),
            ColumnDefinition("sortino_ratio", "REAL DEFAULT 0"),
            ColumnDefinition("profit_factor", "REAL DEFAULT 0"),
            ColumnDefinition("expectancy", "REAL DEFAULT 0"),
        ],
        "market_snapshots": [
            ColumnDefinition("tick_activity_score", "REAL DEFAULT 0"),
            ColumnDefinition("center_crossing_score", "REAL DEFAULT 0"),
            ColumnDefinition("mean_reversion_score", "REAL DEFAULT 0"),
            ColumnDefinition("spread_stability_score", "REAL DEFAULT 0"),
            ColumnDefinition("corridor_quality_score", "REAL DEFAULT 0"),
            ColumnDefinition("order_book_imbalance", "REAL DEFAULT 0"),
            ColumnDefinition("order_book_pressure", "TEXT DEFAULT 'UNKNOWN'"),
            ColumnDefinition("trade_volume_delta", "REAL DEFAULT 0"),
            ColumnDefinition("micro_trend", "TEXT DEFAULT 'UNKNOWN'"),
            ColumnDefinition("relative_volatility", "REAL DEFAULT 0"),
            ColumnDefinition("volatility_regime", "TEXT DEFAULT 'UNKNOWN'"),
            ColumnDefinition("market_health_score", "REAL DEFAULT 0"),
            ColumnDefinition("market_health_status", "TEXT DEFAULT 'UNKNOWN'"),
            ColumnDefinition("market_health_reason", "TEXT DEFAULT ''"),
        ],
        "paper_cycles": [
            ColumnDefinition("strategy_profile", "TEXT DEFAULT 'UNKNOWN'"),
            ColumnDefinition("close_reason", "TEXT"),
            ColumnDefinition("opened_session_id", "TEXT"),
            ColumnDefinition("recovery_status", "TEXT DEFAULT 'ACTIVE'"),
            ColumnDefinition("best_price_after_entry", "REAL"),
            ColumnDefinition("worst_price_after_entry", "REAL"),
            ColumnDefinition("max_favorable_pnl", "REAL DEFAULT 0"),
            ColumnDefinition("max_adverse_pnl", "REAL DEFAULT 0"),
            ColumnDefinition("min_distance_to_target", "REAL"),
            ColumnDefinition("was_target_touched", "INTEGER DEFAULT 0"),
            ColumnDefinition("was_near_target", "INTEGER DEFAULT 0"),
            ColumnDefinition("near_target_threshold", "REAL DEFAULT 0.000005"),
            ColumnDefinition("close_gap_to_target", "REAL"),
            ColumnDefinition("best_possible_pnl", "REAL DEFAULT 0"),
            ColumnDefinition("missed_pnl", "REAL DEFAULT 0"),
            ColumnDefinition("execution_quality_ratio", "REAL DEFAULT 0"),
        ],
        "hf_paper_cycle_entry_diagnostics": [
            ColumnDefinition("session_signal", "INTEGER"),
            ColumnDefinition("velocity_spike_signal", "INTEGER"),
            ColumnDefinition("compression_signal", "INTEGER"),
            ColumnDefinition("signal_strength", "REAL"),
            ColumnDefinition("lead_warning", "TEXT"),
            ColumnDefinition("expected_direction", "TEXT"),
            ColumnDefinition("velocity_value", "REAL"),
            ColumnDefinition("velocity_threshold", "REAL"),
            ColumnDefinition("compression_score", "REAL"),
            ColumnDefinition("compression_threshold", "REAL"),
        ],
    }

    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)

    def run(self) -> list[str]:
        applied: list[str] = []

        with sqlite3.connect(self.db_path) as conn:
            for table_name, columns in self.REQUIRED_COLUMNS.items():
                if not self._table_exists(conn, table_name):
                    continue

                existing_columns = self._get_existing_columns(conn, table_name)

                for column in columns:
                    if column.name in existing_columns:
                        continue

                    conn.execute(
                        f"ALTER TABLE {table_name} ADD COLUMN {column.name} {column.definition}"
                    )
                    applied.append(f"{table_name}.{column.name}")

            if self._table_exists(conn, "paper_cycles"):
                existing_columns = self._get_existing_columns(conn, "paper_cycles")
                if {"id", "cycle_id"}.issubset(existing_columns):
                    cursor = conn.execute(
                        """
                        UPDATE paper_cycles
                        SET cycle_id = id
                        WHERE cycle_id != id
                        """
                    )
                    if cursor.rowcount:
                        applied.append("paper_cycles.cycle_id_backfill")

            conn.commit()

        return applied

    @staticmethod
    def _table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name = ?",
            (table_name,),
        ).fetchone()
        return row is not None

    @staticmethod
    def _get_existing_columns(conn: sqlite3.Connection, table_name: str) -> set[str]:
        rows = conn.execute(f"PRAGMA table_info({table_name})").fetchall()
        return {row[1] for row in rows}
