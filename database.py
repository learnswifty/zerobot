#!/usr/bin/env python3
"""
Production Trading Bot - Database Module
========================================
SQLite database for storing trades, performance, and system logs
"""

import sqlite3
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from contextlib import contextmanager
import json


class TradingDatabase:
    """Database manager for trading bot"""

    def __init__(self, db_path: str = 'data/trades.db'):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.init_database()

    @contextmanager
    def get_connection(self):
        """Context manager for database connection"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable column access by name
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise e
        finally:
            conn.close()

    def init_database(self):
        """Initialize database tables"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Trades table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS trades (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_date DATE NOT NULL,
                    symbol TEXT NOT NULL,
                    direction TEXT NOT NULL,
                    quantity INTEGER NOT NULL,
                    entry_time TIMESTAMP NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_loss REAL NOT NULL,
                    initial_stop_loss REAL NOT NULL,
                    target_price REAL,
                    exit_time TIMESTAMP,
                    exit_price REAL,
                    exit_reason TEXT,
                    pnl REAL DEFAULT 0,
                    pnl_percent REAL DEFAULT 0,
                    max_favorable_excursion REAL DEFAULT 0,
                    max_adverse_excursion REAL DEFAULT 0,
                    status TEXT DEFAULT 'OPEN',
                    order_id_entry TEXT,
                    order_id_exit TEXT,
                    notes TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Daily summary table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS daily_summary (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    trade_date DATE UNIQUE NOT NULL,
                    total_trades INTEGER DEFAULT 0,
                    winning_trades INTEGER DEFAULT 0,
                    losing_trades INTEGER DEFAULT 0,
                    breakeven_trades INTEGER DEFAULT 0,
                    total_pnl REAL DEFAULT 0,
                    win_rate REAL DEFAULT 0,
                    avg_win REAL DEFAULT 0,
                    avg_loss REAL DEFAULT 0,
                    largest_win REAL DEFAULT 0,
                    largest_loss REAL DEFAULT 0,
                    profit_factor REAL DEFAULT 0,
                    starting_capital REAL DEFAULT 0,
                    ending_capital REAL DEFAULT 0,
                    max_drawdown REAL DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # System logs table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS system_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    log_level TEXT NOT NULL,
                    event_type TEXT NOT NULL,
                    message TEXT NOT NULL,
                    details TEXT
                )
            ''')

            # Configuration history table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS config_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    config_data TEXT NOT NULL,
                    notes TEXT
                )
            ''')

            # Create indexes
            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_trades_date 
                ON trades(trade_date)
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_trades_symbol 
                ON trades(symbol)
            ''')

            cursor.execute('''
                CREATE INDEX IF NOT EXISTS idx_trades_status 
                ON trades(status)
            ''')

    def save_trade(self, trade_data: Dict) -> int:
        """Save a new trade to database"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                INSERT INTO trades (
                    trade_date, symbol, direction, quantity,
                    entry_time, entry_price, stop_loss, initial_stop_loss,
                    target_price, status, order_id_entry
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                trade_data['trade_date'],
                trade_data['symbol'],
                trade_data['direction'],
                trade_data['quantity'],
                trade_data['entry_time'],
                trade_data['entry_price'],
                trade_data['stop_loss'],
                trade_data['initial_stop_loss'],
                trade_data.get('target_price'),
                trade_data.get('status', 'OPEN'),
                trade_data.get('order_id_entry')
            ))

            return cursor.lastrowid

    def update_trade(self, trade_id: int, update_data: Dict):
        """Update existing trade"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Build dynamic UPDATE query
            fields = []
            values = []

            for key, value in update_data.items():
                if key != 'id':
                    fields.append(f"{key} = ?")
                    values.append(value)

            # Add updated_at
            fields.append("updated_at = CURRENT_TIMESTAMP")

            query = f"UPDATE trades SET {', '.join(fields)} WHERE id = ?"
            values.append(trade_id)

            cursor.execute(query, values)

    def close_trade(self, trade_id: int, exit_time: datetime, exit_price: float,
                    exit_reason: str, pnl: float, pnl_percent: float,
                    order_id_exit: str = None):
        """Close a trade"""
        update_data = {
            'exit_time': exit_time,
            'exit_price': exit_price,
            'exit_reason': exit_reason,
            'pnl': pnl,
            'pnl_percent': pnl_percent,
            'status': 'CLOSED',
            'order_id_exit': order_id_exit
        }
        self.update_trade(trade_id, update_data)

    def get_open_trades(self, symbol: str = None) -> List[Dict]:
        """Get all open trades"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            if symbol:
                cursor.execute('''
                    SELECT * FROM trades 
                    WHERE status = 'OPEN' AND symbol = ?
                    ORDER BY entry_time DESC
                ''', (symbol,))
            else:
                cursor.execute('''
                    SELECT * FROM trades 
                    WHERE status = 'OPEN'
                    ORDER BY entry_time DESC
                ''')

            return [dict(row) for row in cursor.fetchall()]

    def get_trades_by_date(self, trade_date: str) -> List[Dict]:
        """Get all trades for a specific date"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT * FROM trades 
                WHERE trade_date = ?
                ORDER BY entry_time
            ''', (trade_date,))

            return [dict(row) for row in cursor.fetchall()]

    def get_trade_count_for_stock(self, symbol: str, trade_date: str) -> int:
        """Get number of trades for a stock on a specific date"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT COUNT(*) as count FROM trades 
                WHERE symbol = ? AND trade_date = ?
            ''', (symbol, trade_date))

            result = cursor.fetchone()
            return result['count'] if result else 0

    def get_daily_pnl(self, trade_date: str) -> float:
        """Get total P&L for a specific date"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT COALESCE(SUM(pnl), 0) as total_pnl 
                FROM trades 
                WHERE trade_date = ? AND status = 'CLOSED'
            ''', (trade_date,))

            result = cursor.fetchone()
            return result['total_pnl'] if result else 0.0

    def save_daily_summary(self, summary_data: Dict):
        """Save or update daily summary"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                INSERT OR REPLACE INTO daily_summary (
                    trade_date, total_trades, winning_trades, losing_trades,
                    breakeven_trades, total_pnl, win_rate, avg_win, avg_loss,
                    largest_win, largest_loss, profit_factor,
                    starting_capital, ending_capital, max_drawdown,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (
                summary_data['trade_date'],
                summary_data['total_trades'],
                summary_data['winning_trades'],
                summary_data['losing_trades'],
                summary_data['breakeven_trades'],
                summary_data['total_pnl'],
                summary_data['win_rate'],
                summary_data['avg_win'],
                summary_data['avg_loss'],
                summary_data['largest_win'],
                summary_data['largest_loss'],
                summary_data['profit_factor'],
                summary_data['starting_capital'],
                summary_data['ending_capital'],
                summary_data['max_drawdown']
            ))

    def get_daily_summary(self, trade_date: str) -> Optional[Dict]:
        """Get daily summary for a specific date"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT * FROM daily_summary 
                WHERE trade_date = ?
            ''', (trade_date,))

            result = cursor.fetchone()
            return dict(result) if result else None

    def get_performance_stats(self, days: int = 30) -> Dict:
        """Get performance statistics for last N days"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT 
                    COUNT(*) as total_trades,
                    SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
                    SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
                    SUM(CASE WHEN pnl = 0 THEN 1 ELSE 0 END) as breakeven,
                    SUM(pnl) as total_pnl,
                    AVG(CASE WHEN pnl > 0 THEN pnl END) as avg_win,
                    AVG(CASE WHEN pnl < 0 THEN pnl END) as avg_loss,
                    MAX(pnl) as max_win,
                    MIN(pnl) as max_loss
                FROM trades
                WHERE trade_date >= date('now', '-' || ? || ' days')
                AND status = 'CLOSED'
            ''', (days,))

            result = cursor.fetchone()

            if result and result['total_trades'] > 0:
                stats = dict(result)
                stats['win_rate'] = (stats['wins'] / stats['total_trades'] * 100) if stats['total_trades'] > 0 else 0
                stats['profit_factor'] = abs(stats['avg_win'] / stats['avg_loss']) if stats['avg_loss'] and stats['avg_loss'] != 0 else 0
                return stats

            return {
                'total_trades': 0,
                'wins': 0,
                'losses': 0,
                'breakeven': 0,
                'total_pnl': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'max_win': 0,
                'max_loss': 0,
                'win_rate': 0,
                'profit_factor': 0
            }

    def log_system_event(self, log_level: str, event_type: str, 
                        message: str, details: Dict = None):
        """Log system event"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            details_json = json.dumps(details) if details else None

            cursor.execute('''
                INSERT INTO system_logs (log_level, event_type, message, details)
                VALUES (?, ?, ?, ?)
            ''', (log_level, event_type, message, details_json))

    def save_config(self, config_data: Dict, notes: str = None):
        """Save configuration snapshot"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            config_json = json.dumps(config_data, indent=2)

            cursor.execute('''
                INSERT INTO config_history (config_data, notes)
                VALUES (?, ?)
            ''', (config_json, notes))

    def get_consecutive_losses(self, trade_date: str) -> int:
        """Get count of consecutive losing trades"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                SELECT pnl FROM trades
                WHERE trade_date = ? AND status = 'CLOSED'
                ORDER BY exit_time DESC
            ''', (trade_date,))

            consecutive = 0
            for row in cursor.fetchall():
                if row['pnl'] < 0:
                    consecutive += 1
                else:
                    break

            return consecutive

    def cleanup_old_logs(self, days: int = 90):
        """Clean up old system logs"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute('''
                DELETE FROM system_logs
                WHERE timestamp < date('now', '-' || ? || ' days')
            ''', (days,))

            deleted = cursor.rowcount
            return deleted