#!/usr/bin/env python3
"""
Debug script to check trades in database
"""

import sqlite3
from pathlib import Path

db_path = Path('data/trades.db')

if not db_path.exists():
    print(f"❌ Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

# Get all trades
cursor.execute('SELECT * FROM trades ORDER BY entry_time')
trades = cursor.fetchall()

print(f"{'='*80}")
print(f"TOTAL TRADES IN DATABASE: {len(trades)}")
print(f"{'='*80}\n")

if trades:
    # Group by date and symbol
    cursor.execute('''
        SELECT trade_date, symbol, direction,
               COUNT(*) as count,
               SUM(CASE WHEN pnl > 0 THEN 1 ELSE 0 END) as wins,
               SUM(CASE WHEN pnl < 0 THEN 1 ELSE 0 END) as losses,
               SUM(pnl) as total_pnl,
               status
        FROM trades
        GROUP BY trade_date, symbol, status
        ORDER BY trade_date DESC, symbol
    ''')

    groups = cursor.fetchall()

    print("TRADES BY DATE AND SYMBOL:")
    print(f"{'Date':<15} {'Symbol':<12} {'Status':<8} {'Count':<6} {'Wins':<6} {'Losses':<8} {'P&L':>12}")
    print(f"{'-'*80}")

    for row in groups:
        print(f"{row['trade_date']:<15} {row['symbol']:<12} {row['status']:<8} "
              f"{row['count']:<6} {row['wins']:<6} {row['losses']:<8} ₹{row['total_pnl']:>10.2f}")

    print(f"\n{'-'*80}\n")

    # Show individual trades
    print("INDIVIDUAL TRADES:")
    cursor.execute('''
        SELECT id, trade_date, symbol, direction,
               entry_time, entry_price, exit_time, exit_price,
               pnl, exit_reason, status
        FROM trades
        ORDER BY trade_date DESC, entry_time
        LIMIT 60
    ''')

    individual_trades = cursor.fetchall()
    print(f"{'ID':<5} {'Date':<12} {'Symbol':<10} {'Dir':<6} {'Entry Time':<20} "
          f"{'Entry':<8} {'Exit':<8} {'P&L':>10} {'Reason':<12} {'Status':<8}")
    print(f"{'-'*120}")

    for t in individual_trades:
        entry_time = t['entry_time'][:19] if t['entry_time'] else 'N/A'
        entry_price = f"₹{t['entry_price']:.2f}" if t['entry_price'] else 'N/A'
        exit_price = f"₹{t['exit_price']:.2f}" if t['exit_price'] else 'N/A'
        pnl = f"₹{t['pnl']:.2f}" if t['pnl'] else '₹0.00'
        reason = t['exit_reason'] or '-'

        print(f"{t['id']:<5} {t['trade_date']:<12} {t['symbol']:<10} {t['direction']:<6} "
              f"{entry_time:<20} {entry_price:<8} {exit_price:<8} {pnl:>10} {reason:<12} {t['status']:<8}")
else:
    print("📭 No trades found in database")

conn.close()
