#!/usr/bin/env python3
"""
Test script to verify database save functionality
"""

from database import TradingDatabase
from datetime import datetime

print("Testing database save functionality...\n")

# Initialize database
db = TradingDatabase('data/trades.db')

# Create test trade
trade_data = {
    'trade_date': '2025-10-31',
    'symbol': 'TEST',
    'direction': 'LONG',
    'quantity': 100,
    'entry_time': datetime.now(),
    'entry_price': 150.0,
    'stop_loss': 145.0,
    'initial_stop_loss': 145.0,
    'target_price': 160.0,
    'status': 'OPEN',
    'order_id_entry': 'TEST-123'
}

print("Attempting to save test trade...")
try:
    trade_id = db.save_trade(trade_data)
    print(f"✅ Trade saved successfully! Trade ID: {trade_id}")

    # Verify it was saved
    trades = db.get_trades_by_date('2025-10-31')
    print(f"✅ Verified: Found {len(trades)} trade(s) in database")

    if trades:
        print(f"\nTrade details:")
        print(f"  ID: {trades[0]['id']}")
        print(f"  Symbol: {trades[0]['symbol']}")
        print(f"  Direction: {trades[0]['direction']}")
        print(f"  Entry Price: ₹{trades[0]['entry_price']:.2f}")
        print(f"  Status: {trades[0]['status']}")

    # Clean up test trade
    print(f"\nCleaning up test trade...")
    import sqlite3
    conn = sqlite3.connect('data/trades.db')
    conn.execute('DELETE FROM trades WHERE symbol = "TEST"')
    conn.commit()
    conn.close()
    print("✅ Test trade deleted")

except Exception as e:
    print(f"❌ Error: {str(e)}")
    import traceback
    traceback.print_exc()
