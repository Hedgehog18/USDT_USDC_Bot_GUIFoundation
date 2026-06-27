import sqlite3
from audit.models import DecisionAuditRecord
from datetime import datetime
from pathlib import Path

from paper.models import PaperPortfolio

from storage.database_migration_manager import DatabaseMigrationManager

from market.models import MarketState
from notifications.models import Notification, NotificationLevel
from portfolio.models import BotBudgetEvent
from strategy.models import RiskResult, TradeDecision
from trading.models import Cycle, CycleDirection, CycleStatus, CycleTimeStatus


class DatabaseManager:
    ACTIVE_STATUSES = {
        "CREATED",
        "OPEN_ORDER_PLACED",
        "OPEN_ORDER_FILLED",
        "CLOSE_ORDER_PLACED",
        "CLOSE_ORDER_FILLED",
    }

    def __init__(self, db_path: str = "database/bot.sqlite") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.initialize()
        self.run_migrations()


    def run_migrations(self) -> list[str]:
        migration_manager = DatabaseMigrationManager(self.db_path)
        return migration_manager.run()

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def initialize(self) -> None:
        with self.connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cycles (
                    id INTEGER PRIMARY KEY,
                    mode TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    status TEXT NOT NULL,
                    time_status TEXT NOT NULL,
                    open_price REAL NOT NULL,
                    close_price REAL NOT NULL,
                    amount REAL NOT NULL,
                    target_profit REAL NOT NULL,
                    expected_profit REAL NOT NULL,
                    actual_profit REAL,
                    created_at TEXT NOT NULL,
                    open_filled_at TEXT,
                    close_filled_at TEXT,
                    closed_at TEXT,
                    duration_seconds REAL
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS decision_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    allowed INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    risk_reason TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    price REAL NOT NULL,
                    bid REAL NOT NULL,
                    ask REAL NOT NULL,
                    spread REAL NOT NULL,
                    work_position REAL NOT NULL,
                    short_position REAL NOT NULL,
                    long_position REAL NOT NULL,
                    market_activity_score REAL NOT NULL,
                    cycle_prediction_score REAL NOT NULL,
                    center_confidence TEXT NOT NULL,
                    market_regime TEXT NOT NULL,
                    explanation TEXT NOT NULL,
                    cycle_id INTEGER
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trade_signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    action TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    confidence TEXT NOT NULL,
                    cycle_prediction_score REAL NOT NULL,
                    target_profit REAL NOT NULL,
                    risk_allowed INTEGER NOT NULL,
                    risk_reason TEXT NOT NULL,
                    risk_level TEXT NOT NULL,
                    cycle_id INTEGER
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS market_snapshots (
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
                    tick_activity_score REAL DEFAULT 0,
                    center_crossing_score REAL DEFAULT 0,
                    mean_reversion_score REAL DEFAULT 0,
                    spread_stability_score REAL DEFAULT 0,
                    corridor_quality_score REAL DEFAULT 0,
                    market_activity_score REAL NOT NULL,
                    market_regime TEXT NOT NULL,
                    order_book_imbalance REAL DEFAULT 0,
                    order_book_pressure TEXT DEFAULT 'UNKNOWN',
                    trade_volume_delta REAL DEFAULT 0,
                    micro_trend TEXT DEFAULT 'UNKNOWN',
                    relative_volatility REAL DEFAULT 0,
                    volatility_regime TEXT DEFAULT 'UNKNOWN',
                    market_health_score REAL DEFAULT 0,
                    market_health_status TEXT DEFAULT 'UNKNOWN',
                    market_health_reason TEXT DEFAULT ''
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS market_snapshots_hf (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    price REAL NOT NULL,
                    bid REAL NOT NULL,
                    ask REAL NOT NULL,
                    mid_price REAL NOT NULL,
                    spread REAL NOT NULL,
                    work_position REAL NOT NULL,
                    micro_trend TEXT NOT NULL,
                    entry_zone TEXT NOT NULL,
                    buy_zone INTEGER NOT NULL,
                    sell_zone INTEGER NOT NULL,
                    volatility_regime TEXT NOT NULL,
                    market_regime TEXT NOT NULL,
                    distance_to_long_center REAL NOT NULL,
                    distance_to_short_center REAL NOT NULL,
                    distance_to_work_center REAL NOT NULL,
                    order_book_pressure TEXT NOT NULL,
                    session TEXT NOT NULL,
                    price_change_5_sec REAL NOT NULL,
                    price_change_10_sec REAL NOT NULL,
                    price_change_30_sec REAL NOT NULL,
                    price_change_1_min REAL NOT NULL,
                    price_change_5_min REAL NOT NULL,
                    would_open_cycle INTEGER NOT NULL,
                    reason_if_not TEXT NOT NULL,
                    data_source TEXT NOT NULL
                )
            """)

            conn.execute("CREATE INDEX IF NOT EXISTS idx_market_snapshots_hf_timestamp ON market_snapshots_hf(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_market_snapshots_hf_session ON market_snapshots_hf(session)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_market_snapshots_hf_reason ON market_snapshots_hf(reason_if_not)")

            conn.execute("""
                CREATE TABLE IF NOT EXISTS bot_budget_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    asset TEXT NOT NULL,
                    amount REAL NOT NULL,
                    value_usdt REAL NOT NULL,
                    note TEXT
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    level TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    is_read INTEGER NOT NULL DEFAULT 0,
                    cycle_id INTEGER
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS backtest_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    interval TEXT NOT NULL,
                    candles INTEGER NOT NULL,
                    signals INTEGER NOT NULL,
                    trades INTEGER NOT NULL,
                    winning_trades INTEGER NOT NULL,
                    losing_trades INTEGER NOT NULL,
                    win_rate REAL NOT NULL,
                    gross_profit REAL NOT NULL,
                    total_fees REAL NOT NULL,
                    net_profit REAL NOT NULL,
                    roi REAL NOT NULL,
                    final_value REAL NOT NULL,
                    max_drawdown REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS backtest_trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    trade_index INTEGER NOT NULL,
                    action TEXT NOT NULL,
                    entry_price REAL NOT NULL,
                    exit_price REAL NOT NULL,
                    quantity REAL NOT NULL,
                    gross_profit REAL NOT NULL,
                    fees REAL NOT NULL,
                    net_profit REAL NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES backtest_runs(id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS walk_forward_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    windows INTEGER NOT NULL,
                    average_test_roi REAL NOT NULL,
                    average_test_win_rate REAL NOT NULL,
                    total_test_trades INTEGER NOT NULL,
                    profitable_windows INTEGER NOT NULL,
                    robustness_score REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS walk_forward_windows (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    window_index INTEGER NOT NULL,
                    train_start INTEGER NOT NULL,
                    train_end INTEGER NOT NULL,
                    test_start INTEGER NOT NULL,
                    test_end INTEGER NOT NULL,
                    target_profit REAL NOT NULL,
                    trade_size_percent REAL NOT NULL,
                    train_score REAL NOT NULL,
                    test_score REAL NOT NULL,
                    test_trades INTEGER NOT NULL,
                    test_win_rate REAL NOT NULL,
                    test_net_profit REAL NOT NULL,
                    test_roi REAL NOT NULL,
                    test_max_drawdown REAL NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES walk_forward_runs(id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS backtest_equity_points (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    point_index INTEGER NOT NULL,
                    value REAL NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES backtest_runs(id)
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS backtest_period_analytics (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id INTEGER NOT NULL,
                    period TEXT NOT NULL,
                    start_value REAL NOT NULL,
                    end_value REAL NOT NULL,
                    profit REAL NOT NULL,
                    roi REAL NOT NULL,
                    trades INTEGER NOT NULL,
                    FOREIGN KEY(run_id) REFERENCES backtest_runs(id)
                )
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS paper_orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    order_id INTEGER NOT NULL,
                    side TEXT NOT NULL,
                    price REAL NOT NULL,
                    quantity REAL NOT NULL,
                    notional REAL NOT NULL,
                    status TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    fee REAL NOT NULL,
                    portfolio_usdt REAL NOT NULL,
                    portfolio_usdc REAL NOT NULL,
                    portfolio_value REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS paper_cycles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    cycle_id INTEGER NOT NULL,
                    strategy_profile TEXT DEFAULT 'UNKNOWN',
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
                    closed_at TEXT,
                    close_reason TEXT
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS paper_safety_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    level TEXT NOT NULL,
                    allowed INTEGER NOT NULL,
                    reason TEXT NOT NULL,
                    portfolio_value REAL NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS paper_state_transitions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    previous_state TEXT NOT NULL,
                    new_state TEXT NOT NULL,
                    reason TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS paper_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    iterations INTEGER NOT NULL,
                    opened_cycles INTEGER NOT NULL,
                    closed_cycles INTEGER NOT NULL,
                    safety_stops INTEGER NOT NULL,
                    final_usdt REAL NOT NULL,
                    final_usdc REAL NOT NULL,
                    final_value REAL NOT NULL,
                    rating TEXT NOT NULL,
                    summary TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS long_paper_runs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    iterations INTEGER NOT NULL,
                    interval_seconds INTEGER NOT NULL,
                    final_value REAL NOT NULL,
                    net_profit REAL NOT NULL,
                    win_rate REAL NOT NULL,
                    profit_factor REAL NOT NULL,
                    validation_status TEXT NOT NULL,
                    insights_rating TEXT NOT NULL,
                    summary_report_path TEXT NOT NULL
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS system_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    level TEXT NOT NULL,
                    module TEXT NOT NULL,
                    message TEXT NOT NULL,
                    cycle_id INTEGER
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cycles_status ON cycles(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cycles_created_at ON cycles(created_at)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_trade_signals_timestamp ON trade_signals(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_decision_audit_timestamp ON decision_audit(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_decision_audit_decision ON decision_audit(decision)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_market_snapshots_timestamp ON market_snapshots(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_system_events_timestamp ON system_events(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_paper_orders_timestamp ON paper_orders(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_paper_cycles_timestamp ON paper_cycles(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_paper_cycles_status ON paper_cycles(status)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_paper_safety_events_timestamp ON paper_safety_events(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_paper_state_transitions_timestamp ON paper_state_transitions(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_paper_runs_timestamp ON paper_runs(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_long_paper_runs_timestamp ON long_paper_runs(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_walk_forward_runs_timestamp ON walk_forward_runs(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_walk_forward_windows_run_id ON walk_forward_windows(run_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_backtest_runs_timestamp ON backtest_runs(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_backtest_trades_run_id ON backtest_trades(run_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_backtest_equity_points_run_id ON backtest_equity_points(run_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_backtest_period_analytics_run_id ON backtest_period_analytics(run_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_notifications_timestamp ON notifications(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_notifications_is_read ON notifications(is_read)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_notifications_level ON notifications(level)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bot_budget_events_timestamp ON bot_budget_events(timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_bot_budget_events_type ON bot_budget_events(event_type)")
            conn.commit()

    def save_cycle(self, cycle: Cycle) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO cycles (
                    id, mode, direction, status, time_status,
                    open_price, close_price, amount, target_profit,
                    expected_profit, actual_profit,
                    created_at, open_filled_at, close_filled_at, closed_at,
                    duration_seconds
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cycle.id,
                    cycle.mode,
                    cycle.direction.value,
                    cycle.status.value,
                    cycle.time_status.value,
                    cycle.open_price,
                    cycle.close_price,
                    cycle.amount,
                    cycle.target_profit,
                    cycle.expected_profit,
                    cycle.actual_profit,
                    cycle.created_at.isoformat(),
                    cycle.open_filled_at.isoformat() if cycle.open_filled_at else None,
                    cycle.close_filled_at.isoformat() if cycle.close_filled_at else None,
                    cycle.closed_at.isoformat() if cycle.closed_at else None,
                    cycle.duration_seconds,
                ),
            )
            conn.commit()

    def load_active_cycles(self) -> list[Cycle]:
        placeholders = ",".join("?" for _ in self.ACTIVE_STATUSES)

        with self.connect() as conn:
            rows = conn.execute(
                f"SELECT * FROM cycles WHERE status IN ({placeholders}) ORDER BY created_at ASC",
                tuple(self.ACTIVE_STATUSES),
            ).fetchall()

        return [self._row_to_cycle(row) for row in rows]

    def _row_to_cycle(self, row: tuple) -> Cycle:
        (
            cycle_id,
            mode,
            direction,
            status,
            time_status,
            open_price,
            close_price,
            amount,
            target_profit,
            expected_profit,
            actual_profit,
            created_at,
            open_filled_at,
            close_filled_at,
            closed_at,
            _duration_seconds,
        ) = row

        return Cycle(
            id=int(cycle_id),
            mode=mode,
            direction=CycleDirection(direction),
            status=CycleStatus(status),
            time_status=CycleTimeStatus(time_status),
            open_price=float(open_price),
            close_price=float(close_price),
            amount=float(amount),
            target_profit=float(target_profit),
            expected_profit=float(expected_profit),
            actual_profit=actual_profit,
            created_at=datetime.fromisoformat(created_at),
            open_filled_at=datetime.fromisoformat(open_filled_at) if open_filled_at else None,
            close_filled_at=datetime.fromisoformat(close_filled_at) if close_filled_at else None,
            closed_at=datetime.fromisoformat(closed_at) if closed_at else None,
        )

    def save_trade_signal(self, decision: TradeDecision, risk_result: RiskResult, cycle_id: int | None = None) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO trade_signals (
                    timestamp, action, reason, confidence,
                    cycle_prediction_score, target_profit,
                    risk_allowed, risk_reason, risk_level, cycle_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    decision.created_at.isoformat(),
                    decision.action,
                    decision.reason,
                    decision.confidence,
                    decision.cycle_prediction_score,
                    decision.target_profit,
                    1 if risk_result.allowed else 0,
                    risk_result.reason,
                    risk_result.risk_level,
                    cycle_id,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def save_market_snapshot(self, market_state: MarketState) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO market_snapshots (
                    timestamp, symbol, price, bid, ask, spread,
                    work_center, work_position,
                    short_center, short_position,
                    long_center, long_position,
                    center_confidence, center_alignment,
                    tick_activity_score, center_crossing_score,
                    mean_reversion_score, spread_stability_score,
                    corridor_quality_score,
                    market_activity_score, market_regime,
                    order_book_imbalance, order_book_pressure,
                    trade_volume_delta, micro_trend,
                    relative_volatility, volatility_regime,
                    market_health_score, market_health_status, market_health_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    market_state.created_at.isoformat(),
                    market_state.symbol,
                    market_state.price,
                    market_state.bid,
                    market_state.ask,
                    market_state.spread,
                    market_state.work_center,
                    market_state.work_position,
                    market_state.short_center,
                    market_state.short_position,
                    market_state.long_center,
                    market_state.long_position,
                    market_state.center_confidence,
                    market_state.center_alignment,
                    market_state.tick_activity_score,
                    market_state.center_crossing_score,
                    market_state.mean_reversion_score,
                    market_state.spread_stability_score,
                    market_state.corridor_quality_score,
                    market_state.market_activity_score,
                    market_state.market_regime,
                    market_state.order_book_imbalance,
                    market_state.order_book_pressure,
                    market_state.trade_volume_delta,
                    market_state.micro_trend,
                    market_state.relative_volatility,
                    market_state.volatility_regime,
                    market_state.market_health_score,
                    market_state.market_health_status,
                    market_state.market_health_reason,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def save_system_event(self, level: str, module: str, message: str, cycle_id: int | None = None) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO system_events (
                    timestamp, level, module, message, cycle_id
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    datetime.utcnow().isoformat(),
                    level,
                    module,
                    message,
                    cycle_id,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def save_hf_market_snapshot(self, snapshot: dict) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO market_snapshots_hf (
                    timestamp, symbol, price, bid, ask, mid_price, spread,
                    work_position, micro_trend, entry_zone, buy_zone, sell_zone,
                    volatility_regime, market_regime,
                    distance_to_long_center, distance_to_short_center, distance_to_work_center,
                    order_book_pressure, session,
                    price_change_5_sec, price_change_10_sec, price_change_30_sec,
                    price_change_1_min, price_change_5_min,
                    would_open_cycle, reason_if_not, data_source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot["timestamp"],
                    snapshot["symbol"],
                    snapshot["price"],
                    snapshot["bid"],
                    snapshot["ask"],
                    snapshot["mid_price"],
                    snapshot["spread"],
                    snapshot["work_position"],
                    snapshot["micro_trend"],
                    snapshot["entry_zone"],
                    int(bool(snapshot["buy_zone"])),
                    int(bool(snapshot["sell_zone"])),
                    snapshot["volatility_regime"],
                    snapshot["market_regime"],
                    snapshot["distance_to_long_center"],
                    snapshot["distance_to_short_center"],
                    snapshot["distance_to_work_center"],
                    snapshot["order_book_pressure"],
                    snapshot["session"],
                    snapshot["price_change_5_sec"],
                    snapshot["price_change_10_sec"],
                    snapshot["price_change_30_sec"],
                    snapshot["price_change_1_min"],
                    snapshot["price_change_5_min"],
                    int(bool(snapshot["would_open_cycle"])),
                    snapshot["reason_if_not"],
                    snapshot["data_source"],
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def load_recent_hf_market_snapshots(self, limit: int = 5000) -> list[tuple]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT timestamp, price
                FROM market_snapshots_hf
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def load_recent_system_events(self, limit: int = 200) -> list[tuple]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT timestamp, level, module, message
                FROM system_events
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def load_latest_system_event(self):
        rows = self.load_recent_system_events(limit=1)
        return rows[0] if rows else None

    def load_latest_signal(self):
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT timestamp, action, confidence, reason
                FROM trade_signals
                ORDER BY timestamp DESC, id DESC
                LIMIT 1
                """
            ).fetchone()

    def load_latest_cycle(self):
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT id, direction, status, open_price, close_price, actual_profit
                FROM cycles
                ORDER BY created_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()

    def count_rows(self, table: str) -> int:
        allowed_tables = {"cycles", "trade_signals", "market_snapshots", "market_snapshots_hf", "system_events", "bot_budget_events", "notifications", "decision_audit", "backtest_runs", "backtest_trades", "walk_forward_runs", "walk_forward_windows", "backtest_equity_points", "backtest_period_analytics", "paper_orders", "paper_cycles", "paper_safety_events", "paper_state_transitions", "paper_runs"}
        if table not in allowed_tables:
            raise ValueError("Table is not allowed.")
        with self.connect() as conn:
            row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            return int(row[0])


    def count_cycles_total(self) -> int:
        return self.count_rows("cycles")

    def count_cycles_by_status(self, status: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM cycles WHERE status = ?",
                (status,),
            ).fetchone()
            return int(row[0])

    def count_active_cycles(self) -> int:
        placeholders = ",".join("?" for _ in self.ACTIVE_STATUSES)
        with self.connect() as conn:
            row = conn.execute(
                f"SELECT COUNT(*) FROM cycles WHERE status IN ({placeholders})",
                tuple(self.ACTIVE_STATUSES),
            ).fetchone()
            return int(row[0])

    def count_winning_cycles(self) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM cycles WHERE status = 'CLOSED' AND actual_profit > 0"
            ).fetchone()
            return int(row[0])

    def sum_realized_profit(self) -> float:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(SUM(actual_profit), 0) FROM cycles WHERE status = 'CLOSED'"
            ).fetchone()
            return float(row[0])


    def save_bot_budget_event(self, event: BotBudgetEvent) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO bot_budget_events (
                    timestamp, event_type, asset, amount, value_usdt, note
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    event.created_at.isoformat(),
                    event.event_type,
                    event.asset,
                    event.amount,
                    event.value_usdt,
                    event.note,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def load_bot_budget_events(self) -> list[BotBudgetEvent]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT timestamp, event_type, asset, amount, value_usdt, note
                FROM bot_budget_events
                ORDER BY timestamp ASC
                """
            ).fetchall()

        from datetime import datetime

        return [
            BotBudgetEvent(
                created_at=datetime.fromisoformat(row[0]),
                event_type=row[1],
                asset=row[2],
                amount=float(row[3]),
                value_usdt=float(row[4]),
                note=row[5] or "",
            )
            for row in rows
        ]

    def sum_total_deposits(self) -> float:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(value_usdt), 0)
                FROM bot_budget_events
                WHERE event_type = 'DEPOSIT'
                """
            ).fetchone()
            return float(row[0])

    def sum_removed_from_budget(self) -> float:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(SUM(value_usdt), 0)
                FROM bot_budget_events
                WHERE event_type = 'WITHDRAW_FROM_BOT_BUDGET'
                """
            ).fetchone()
            return float(row[0])

    def calculate_net_deposits(self) -> float:
        return self.sum_total_deposits() - self.sum_removed_from_budget()


    def average_closed_cycle_duration(self) -> float:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT COALESCE(AVG(duration_seconds), 0)
                FROM cycles
                WHERE status = 'CLOSED'
                """
            ).fetchone()
            return float(row[0])

    def count_trade_signals_total(self) -> int:
        return self.count_rows("trade_signals")

    def count_trade_signals_by_action(self, action: str) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM trade_signals WHERE action = ?",
                (action,),
            ).fetchone()
            return int(row[0])

    def count_allowed_trade_signals(self) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM trade_signals WHERE risk_allowed = 1"
            ).fetchone()
            return int(row[0])

    def average_cycle_prediction_score(self) -> float:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COALESCE(AVG(cycle_prediction_score), 0) FROM trade_signals"
            ).fetchone()
            return float(row[0])


    def save_notification(self, notification: Notification) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO notifications (
                    timestamp, level, title, message, is_read, cycle_id
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    notification.created_at.isoformat(),
                    notification.level.value,
                    notification.title,
                    notification.message,
                    1 if notification.is_read else 0,
                    notification.cycle_id,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def count_unread_notifications(self) -> int:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM notifications WHERE is_read = 0"
            ).fetchone()
            return int(row[0])

    def mark_all_notifications_as_read(self) -> None:
        with self.connect() as conn:
            conn.execute("UPDATE notifications SET is_read = 1 WHERE is_read = 0")
            conn.commit()

    def load_recent_notifications(self, limit: int = 20) -> list[Notification]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT timestamp, level, title, message, is_read, cycle_id
                FROM notifications
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        from datetime import datetime

        return [
            Notification(
                created_at=datetime.fromisoformat(row[0]),
                level=NotificationLevel(row[1]),
                title=row[2],
                message=row[3],
                is_read=bool(row[4]),
                cycle_id=row[5],
            )
            for row in rows
        ]


    def save_decision_audit(self, record: DecisionAuditRecord) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO decision_audit (
                    timestamp, decision, allowed, reason, risk_reason,
                    symbol, price, bid, ask, spread,
                    work_position, short_position, long_position,
                    market_activity_score, cycle_prediction_score,
                    center_confidence, market_regime,
                    explanation, cycle_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    record.timestamp.isoformat(),
                    record.decision,
                    1 if record.allowed else 0,
                    record.reason,
                    record.risk_reason,
                    record.symbol,
                    record.price,
                    record.bid,
                    record.ask,
                    record.spread,
                    record.work_position,
                    record.short_position,
                    record.long_position,
                    record.market_activity_score,
                    record.cycle_prediction_score,
                    record.center_confidence,
                    record.market_regime,
                    record.explanation,
                    record.cycle_id,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def load_recent_decision_audit(self, limit: int = 20) -> list[tuple]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT timestamp, decision, allowed, reason, risk_reason, explanation, cycle_id
                FROM decision_audit
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()


    def save_backtest_result(self, result, trades: list) -> int:
        from datetime import datetime

        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO backtest_runs (
                    timestamp, symbol, interval, candles, signals, trades,
                    winning_trades, losing_trades, win_rate,
                    gross_profit, total_fees, net_profit, roi,
                    final_value, max_drawdown
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.utcnow().isoformat(),
                    result.symbol,
                    result.interval,
                    result.candles,
                    result.signals,
                    result.trades,
                    result.winning_trades,
                    result.losing_trades,
                    result.win_rate,
                    result.gross_profit,
                    result.total_fees,
                    result.net_profit,
                    result.roi,
                    result.final_value,
                    result.max_drawdown,
                ),
            )
            run_id = int(cursor.lastrowid)

            for trade in trades:
                conn.execute(
                    """
                    INSERT INTO backtest_trades (
                        run_id, trade_index, action, entry_price, exit_price,
                        quantity, gross_profit, fees, net_profit
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        trade.index,
                        trade.action,
                        trade.entry_price,
                        trade.exit_price,
                        trade.quantity,
                        trade.gross_profit,
                        trade.fees,
                        trade.net_profit,
                    ),
                )

            conn.commit()
            return run_id

    def load_recent_backtest_runs(self, limit: int = 10) -> list[tuple]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT id, timestamp, symbol, interval, candles, trades,
                       win_rate, net_profit, roi, max_drawdown
                FROM backtest_runs
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def load_latest_backtest_run(self):
        rows = self.load_recent_backtest_runs(limit=1)
        return rows[0] if rows else None

    def load_backtest_equity_points(self, run_id: int) -> list[tuple]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT point_index, value
                FROM backtest_equity_points
                WHERE run_id = ?
                ORDER BY point_index ASC
                """,
                (run_id,),
            ).fetchall()

    def load_backtest_trades(self, run_id: int) -> list[tuple]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT trade_index, action, entry_price, exit_price,
                       quantity, gross_profit, fees, net_profit
                FROM backtest_trades
                WHERE run_id = ?
                ORDER BY trade_index ASC
                """,
                (run_id,),
            ).fetchall()


    def save_walk_forward_result(self, result, windows: list) -> int:
        from datetime import datetime

        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO walk_forward_runs (
                    timestamp, windows, average_test_roi, average_test_win_rate,
                    total_test_trades, profitable_windows, robustness_score
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.utcnow().isoformat(),
                    result.windows,
                    result.average_test_roi,
                    result.average_test_win_rate,
                    result.total_test_trades,
                    result.profitable_windows,
                    result.robustness_score,
                ),
            )
            run_id = int(cursor.lastrowid)

            for item in windows:
                conn.execute(
                    """
                    INSERT INTO walk_forward_windows (
                        run_id, window_index, train_start, train_end,
                        test_start, test_end, target_profit, trade_size_percent,
                        train_score, test_score, test_trades, test_win_rate,
                        test_net_profit, test_roi, test_max_drawdown
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        item.window_index,
                        item.train_start,
                        item.train_end,
                        item.test_start,
                        item.test_end,
                        item.best_parameters.target_profit,
                        item.best_parameters.trade_size_percent,
                        item.train_score,
                        item.test_score,
                        item.test_result.trades,
                        item.test_result.win_rate,
                        item.test_result.net_profit,
                        item.test_result.roi,
                        item.test_result.max_drawdown,
                    ),
                )

            conn.commit()
            return run_id

    def load_recent_walk_forward_runs(self, limit: int = 10) -> list[tuple]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT id, timestamp, windows, average_test_roi, average_test_win_rate,
                       total_test_trades, profitable_windows, robustness_score
                FROM walk_forward_runs
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()


    def save_backtest_equity_points(self, run_id: int, equity_points: list) -> None:
        with self.connect() as conn:
            for point in equity_points:
                conn.execute(
                    """
                    INSERT INTO backtest_equity_points (
                        run_id, point_index, value
                    ) VALUES (?, ?, ?)
                    """,
                    (run_id, point.index, point.value),
                )
            conn.commit()

    def save_backtest_period_analytics(self, run_id: int, periods: list) -> None:
        with self.connect() as conn:
            for period in periods:
                conn.execute(
                    """
                    INSERT INTO backtest_period_analytics (
                        run_id, period, start_value, end_value, profit, roi, trades
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        run_id,
                        period.period,
                        period.start_value,
                        period.end_value,
                        period.profit,
                        period.roi,
                        period.trades,
                    ),
                )
            conn.commit()

    def load_backtest_period_analytics(self, run_id: int) -> list[tuple]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT period, start_value, end_value, profit, roi, trades
                FROM backtest_period_analytics
                WHERE run_id = ?
                ORDER BY id ASC
                """,
                (run_id,),
            ).fetchall()


    def save_paper_execution(self, execution) -> int:
        from datetime import datetime

        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO paper_orders (
                    timestamp, order_id, side, price, quantity, notional,
                    status, reason, fee, portfolio_usdt, portfolio_usdc, portfolio_value
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.utcnow().isoformat(),
                    execution.order.id,
                    execution.order.side.value,
                    execution.order.price,
                    execution.order.quantity,
                    execution.order.notional,
                    execution.order.status.value,
                    execution.order.reason,
                    execution.fee,
                    execution.portfolio.usdt,
                    execution.portfolio.usdc,
                    execution.portfolio.total_value,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def load_recent_paper_orders(self, limit: int = 20) -> list[tuple]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT timestamp, order_id, side, price, quantity, notional,
                       status, reason, fee, portfolio_usdt, portfolio_usdc, portfolio_value
                FROM paper_orders
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()


    def save_paper_cycle(self, cycle, strategy_profile: str = "UNKNOWN") -> int:
        from datetime import datetime

        close_reason = getattr(cycle, "close_reason", None)
        with self.connect() as conn:
            if cycle.status.value != "OPEN":
                cursor = conn.execute(
                    """
                    UPDATE paper_cycles
                    SET timestamp = ?, strategy_profile = ?, status = ?,
                        close_price = ?, close_fee = ?, gross_profit = ?,
                        net_profit = ?, closed_at = ?, close_reason = ?
                    WHERE id = ? AND status = 'OPEN'
                    """,
                    (
                        datetime.utcnow().isoformat(),
                        strategy_profile,
                        cycle.status.value,
                        cycle.close_price,
                        cycle.close_fee,
                        cycle.gross_profit,
                        cycle.net_profit,
                        cycle.closed_at.isoformat() if cycle.closed_at else None,
                        close_reason,
                        cycle.id,
                    ),
                )
                if cursor.rowcount:
                    conn.commit()
                    return int(cycle.id)

            cursor = conn.execute(
                """
                INSERT INTO paper_cycles (
                    timestamp, cycle_id, strategy_profile, direction, status, open_price, close_price,
                    quantity, open_fee, close_fee, gross_profit, net_profit,
                    opened_at, closed_at, close_reason
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.utcnow().isoformat(),
                    cycle.id,
                    strategy_profile,
                    cycle.direction.value,
                    cycle.status.value,
                    cycle.open_price,
                    cycle.close_price,
                    cycle.quantity,
                    cycle.open_fee,
                    cycle.close_fee,
                    cycle.gross_profit,
                    cycle.net_profit,
                    cycle.opened_at.isoformat(),
                    cycle.closed_at.isoformat() if cycle.closed_at else None,
                    close_reason,
                ),
            )
            row_id = int(cursor.lastrowid)
            if cycle.status.value == "OPEN":
                conn.execute(
                    "UPDATE paper_cycles SET cycle_id = ? WHERE id = ?",
                    (row_id, row_id),
                )
                cycle.id = row_id
            conn.commit()
            return row_id

    def load_recent_paper_cycles(self, limit: int = 20) -> list[tuple]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT timestamp, cycle_id, direction, status, open_price, close_price,
                       quantity, open_fee, close_fee, gross_profit, net_profit
                FROM paper_cycles
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def load_recent_paper_cycles_by_profile(self, strategy_profile: str, limit: int = 500) -> list[tuple]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT timestamp, cycle_id, direction, status, open_price, close_price,
                       quantity, open_fee, close_fee, gross_profit, net_profit
                FROM paper_cycles
                WHERE strategy_profile = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (strategy_profile, limit),
            ).fetchall()

    def load_recent_paper_cycles_for_safety(
        self,
        strategy_profile: str,
        *,
        baseline_max_id: int = 0,
        limit: int = 500,
    ) -> list[tuple]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT timestamp, cycle_id, direction, status, open_price, close_price,
                       quantity, open_fee, close_fee, gross_profit, net_profit, close_reason
                FROM paper_cycles
                WHERE strategy_profile = ? AND id > ?
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (strategy_profile, baseline_max_id, limit),
            ).fetchall()


    def save_paper_safety_event(self, result, portfolio_value: float) -> int:
        from datetime import datetime

        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO paper_safety_events (
                    timestamp, level, allowed, reason, portfolio_value
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (
                    datetime.utcnow().isoformat(),
                    result.level,
                    1 if result.allowed else 0,
                    result.reason,
                    portfolio_value,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def load_recent_paper_safety_events(self, limit: int = 20) -> list[tuple]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT timestamp, level, allowed, reason, portfolio_value
                FROM paper_safety_events
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()



    def save_paper_state_transition(self, transition) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO paper_state_transitions (
                    timestamp, previous_state, new_state, reason
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    transition.created_at.isoformat(),
                    transition.previous_state.value,
                    transition.new_state.value,
                    transition.reason,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def load_last_paper_portfolio(self):
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT portfolio_usdt, portfolio_usdc, price
                FROM paper_orders
                ORDER BY timestamp DESC
                LIMIT 1
                """
            ).fetchone()

        if row is None:
            return None

        return PaperPortfolio(usdt=float(row[0]), usdc=float(row[1]), usdc_price=float(row[2]))

    def count_open_paper_cycles(self) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT COUNT(*) FROM paper_cycles WHERE status = 'OPEN'").fetchone()
            return int(row[0])

    def load_last_paper_cycle_summary(self):
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT status, net_profit
                FROM paper_cycles
                ORDER BY timestamp DESC
                LIMIT 1
                """
            ).fetchone()

    def load_recent_paper_state_transitions(self, limit: int = 20) -> list[tuple]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT timestamp, previous_state, new_state, reason
                FROM paper_state_transitions
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()


    def save_paper_run(self, result, insights) -> int:
        from datetime import datetime

        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO paper_runs (
                    timestamp, iterations, opened_cycles, closed_cycles,
                    safety_stops, final_usdt, final_usdc, final_value,
                    rating, summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.utcnow().isoformat(),
                    result.iterations,
                    result.opened_cycles,
                    result.closed_cycles,
                    result.safety_stops,
                    result.final_portfolio.usdt,
                    result.final_portfolio.usdc,
                    result.final_portfolio.total_value,
                    insights.rating,
                    insights.summary,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def load_recent_paper_runs(self, limit: int = 20) -> list[tuple]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT id, timestamp, iterations, opened_cycles, closed_cycles,
                       safety_stops, final_usdt, final_usdc, final_value,
                       rating, summary
                FROM paper_runs
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def load_recent_paper_cycles_with_identity(self, limit: int = 20) -> list[tuple]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT id, timestamp, cycle_id, strategy_profile, direction, status,
                       open_price, close_price, quantity, open_fee, close_fee,
                       gross_profit, net_profit
                FROM paper_cycles
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def load_open_paper_cycles(self, limit: int = 100) -> list[tuple]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT id, timestamp, cycle_id, strategy_profile, direction, status,
                       open_price, close_price, quantity, open_fee, close_fee,
                       gross_profit, net_profit, opened_at, closed_at
                FROM paper_cycles
                WHERE status = 'OPEN'
                ORDER BY opened_at ASC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

    def load_open_paper_cycle_by_id(self, db_id: int) -> tuple | None:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT id, timestamp, cycle_id, strategy_profile, direction, status,
                       open_price, close_price, quantity, open_fee, close_fee,
                       gross_profit, net_profit, opened_at, closed_at
                FROM paper_cycles
                WHERE id = ? AND status = 'OPEN'
                """,
                (db_id,),
            ).fetchone()

    def close_paper_cycle_manually(
        self,
        *,
        db_id: int,
        close_price: float,
        close_fee: float,
        gross_profit: float,
        net_profit: float,
        close_reason: str,
        closed_at: str,
    ) -> bool:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                UPDATE paper_cycles
                SET timestamp = ?,
                    status = 'CLOSED_MANUAL',
                    close_price = ?,
                    close_fee = ?,
                    gross_profit = ?,
                    net_profit = ?,
                    close_reason = ?,
                    closed_at = ?
                WHERE id = ? AND status = 'OPEN'
                """,
                (
                    closed_at,
                    close_price,
                    close_fee,
                    gross_profit,
                    net_profit,
                    close_reason,
                    closed_at,
                    db_id,
                ),
            )
            conn.commit()
            return bool(cursor.rowcount)

    def load_paper_cycle_collection_stats(self, strategy_profile: str) -> dict[str, float | int]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN status = 'CLOSED' THEN 1 ELSE 0 END), 0) AS closed_cycles,
                    COALESCE(SUM(CASE WHEN status = 'OPEN' THEN 1 ELSE 0 END), 0) AS open_cycles,
                    COALESCE(SUM(CASE WHEN status = 'CLOSED' THEN net_profit ELSE 0 END), 0) AS net_profit,
                    COALESCE(SUM(CASE WHEN status = 'CLOSED' AND net_profit > 0 THEN 1 ELSE 0 END), 0) AS winning_cycles
                FROM paper_cycles
                WHERE strategy_profile = ?
                """,
                (strategy_profile,),
            ).fetchone()

        closed_cycles = int(row[0])
        winning_cycles = int(row[3])
        return {
            "closed_cycles": closed_cycles,
            "open_cycles": int(row[1]),
            "net_profit": float(row[2]),
            "winning_cycles": winning_cycles,
            "win_rate": (winning_cycles / closed_cycles) if closed_cycles else 0.0,
        }

    def load_paper_cycle_collection_baseline(self, strategy_profile: str) -> dict[str, float | int]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COALESCE(MAX(id), 0) AS max_cycle_id,
                    COALESCE(SUM(CASE WHEN status = 'CLOSED' THEN 1 ELSE 0 END), 0) AS closed_cycles,
                    COALESCE(SUM(CASE WHEN status = 'CLOSED' THEN net_profit ELSE 0 END), 0) AS net_profit
                FROM paper_cycles
                WHERE strategy_profile = ?
                """,
                (strategy_profile,),
            ).fetchone()

        return {
            "max_cycle_id": int(row[0]),
            "closed_cycles": int(row[1]),
            "net_profit": float(row[2]),
        }

    def load_new_paper_cycle_collection_stats(self, strategy_profile: str, baseline_max_id: int) -> dict[str, float | int]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT
                    COALESCE(SUM(CASE WHEN status IN ('CLOSED', 'CLOSED_MANUAL') THEN 1 ELSE 0 END), 0) AS closed_cycles,
                    COALESCE(SUM(CASE WHEN status = 'CLOSED' THEN 1 ELSE 0 END), 0) AS automatic_closed,
                    COALESCE(SUM(CASE WHEN status = 'CLOSED_MANUAL' THEN 1 ELSE 0 END), 0) AS manual_closed,
                    COALESCE(SUM(CASE WHEN status = 'CLOSED' AND close_reason = 'target' THEN 1 ELSE 0 END), 0) AS target_closed,
                    COALESCE(SUM(CASE WHEN status = 'CLOSED' AND close_reason LIKE 'max_holding_%' THEN 1 ELSE 0 END), 0) AS timeout_closed,
                    COALESCE(SUM(CASE WHEN status = 'OPEN' THEN 1 ELSE 0 END), 0) AS open_cycles,
                    COALESCE(SUM(CASE WHEN status IN ('CLOSED', 'CLOSED_MANUAL') THEN net_profit ELSE 0 END), 0) AS net_profit,
                    COALESCE(SUM(CASE WHEN status IN ('CLOSED', 'CLOSED_MANUAL') AND net_profit > 0 THEN 1 ELSE 0 END), 0) AS winning_cycles
                FROM paper_cycles
                WHERE strategy_profile = ? AND id > ?
                """,
                (strategy_profile, baseline_max_id),
            ).fetchone()

        closed_cycles = int(row[0])
        winning_cycles = int(row[7])
        return {
            "closed_cycles": closed_cycles,
            "automatic_closed": int(row[1]),
            "manual_closed": int(row[2]),
            "target_closed": int(row[3]),
            "timeout_closed": int(row[4]),
            "open_cycles": int(row[5]),
            "net_profit": float(row[6]),
            "winning_cycles": winning_cycles,
            "win_rate": (winning_cycles / closed_cycles) if closed_cycles else 0.0,
        }

    def save_long_paper_run(
        self,
        *,
        iterations: int,
        interval_seconds: int,
        final_value: float,
        net_profit: float,
        win_rate: float,
        profit_factor: float,
        validation_status: str,
        insights_rating: str,
        summary_report_path: str,
    ) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO long_paper_runs (
                    timestamp, iterations, interval_seconds, final_value,
                    net_profit, win_rate, profit_factor, validation_status,
                    insights_rating, summary_report_path
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    datetime.utcnow().isoformat(),
                    iterations,
                    interval_seconds,
                    final_value,
                    net_profit,
                    win_rate,
                    profit_factor,
                    validation_status,
                    insights_rating,
                    summary_report_path,
                ),
            )
            conn.commit()
            return int(cursor.lastrowid)

    def load_recent_long_paper_runs(self, limit: int = 20) -> list[tuple]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT id, timestamp, iterations, interval_seconds,
                       final_value, net_profit, win_rate, profit_factor,
                       validation_status, insights_rating, summary_report_path
                FROM long_paper_runs
                ORDER BY timestamp DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
