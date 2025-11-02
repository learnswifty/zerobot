# Zerobot - Quick Reference Guide

## Navigation Guide

This repository contains a comprehensive trading bot with Paper and Live trading modes.

**Start here:**
1. `README.md` - Overview
2. `PAPER_VS_LIVE_TRADING.md` - Complete detailed analysis (PRIMARY DOCUMENT)
3. `ARCHITECTURE_SUMMARY.md` - Visual diagrams and architecture
4. `INTERACTIVE_MODE_GUIDE.md` - How to use the bot
5. `TEST_BACKTEST.md` - Testing information

---

## Core Files Map

```
/home/user/zerobot/
├── config.py                          # Configuration (77 = mode toggle)
├── trading_bot.py                     # Main bot logic
│   ├── OrderManager (lines 157-298)   # Order execution (PAPER vs LIVE)
│   ├── Trade (lines 90-155)           # Trade object definition
│   ├── CircuitBreaker (lines 300-350) # Risk management
│   └── TradingBot (lines 352+)        # Main class
├── database.py                        # SQLite database
├── command_handler.py                 # Runtime commands
├── logger.py                          # Logging system
├── intra_back_5_exit.py               # Backtesting engine
└── PAPER_VS_LIVE_TRADING.md          # Detailed analysis (READ THIS)
```

---

## One Sentence Summary

**The bot uses a single config flag (`ENABLE_PAPER_TRADING = True/False`) to switch between simulated trading and real API orders.**

---

## Paper vs Live: The Key Differences

### Paper Mode (Simulated)
- **When**: `ENABLE_PAPER_TRADING = True`
- **Order ID**: `PAPER-1730520600000` (timestamp-based)
- **Execution**: In-memory dictionary, instant COMPLETE
- **Risk**: NO real money
- **Best For**: Testing strategy, learning, backtesting

### Live Mode (Real)
- **When**: `ENABLE_PAPER_TRADING = False` (requires "CONFIRM")
- **Order ID**: Real Zerodha ID from exchange
- **Execution**: Zerodha API with 3 retries, polls for status
- **Risk**: REAL capital at stake
- **Best For**: After paper testing is successful

---

## Where to Find Specific Information

### To understand Paper Trading
- **File**: `PAPER_VS_LIVE_TRADING.md` - Section 1
- **Lines**: trading_bot.py, 179-206 (place_order paper logic)
- **Key Class**: OrderManager, section "if self.paper_mode:"

### To understand Live Trading
- **File**: `PAPER_VS_LIVE_TRADING.md` - Section 2
- **Lines**: trading_bot.py, 207-239 (place_order live logic)
- **Key Class**: OrderManager, section "for attempt in range(self.retry_count):"

### To understand Order Execution
- **File**: `PAPER_VS_LIVE_TRADING.md` - Section 5
- **Key Method**: OrderManager.place_order() (lines 170-239)
- **Monitoring**: OrderManager.wait_for_order_completion() (lines 261-281)

### To understand Position Tracking
- **File**: `PAPER_VS_LIVE_TRADING.md` - Section 6
- **Key Class**: Trade (lines 90-155)
- **Active Trades**: TradingBot.active_trades (line 398)
- **Monitoring**: TradingBot.monitor_active_trades() (lines 1023-1099)

### To understand Risk Management
- **File**: `PAPER_VS_LIVE_TRADING.md` - Section 7
- **Config File**: config.py (lines 76-88)
- **Circuit Breaker**: trading_bot.py (lines 300-350)
- **Position Sizing**: trading_bot.py (lines 737-757)
- **Stop Loss Validation**: trading_bot.py (lines 783-802)

---

## Configuration Toggle

**To switch modes**, edit `config.py`:

```python
# Line 77
ENABLE_PAPER_TRADING = True    # Paper mode (safe)
# OR
ENABLE_PAPER_TRADING = False   # Live mode (real money)
```

**Or use runtime prompt:**
```
python trading_bot.py
# Select option 1 for Paper
# Select option 2 for Live (requires "CONFIRM")
```

---

## Risk Management Settings

All in `config.py`:

```python
DEFAULT_CAPITAL = 10000          # Starting money
DEFAULT_LEVERAGE = 5.0           # Buying power multiplier
MAX_DAILY_LOSS_PERCENT = 5.0     # Stop if 5% daily loss
MAX_DAILY_TRADES = 10            # Max trades per day
MAX_ENTRIES_PER_STOCK = 2        # Max 2 entries per stock
MAX_OPEN_POSITIONS = 5           # Max 5 simultaneous trades
MAX_STOP_LOSS_PERCENT = 5.0      # Max SL %
MIN_STOP_LOSS_PERCENT = 0.5      # Min SL %
```

**Circuit Breaker:**
```python
CIRCUIT_BREAKER_LOSS_THRESHOLD = 1500          # Stop if lose ₹1500
CIRCUIT_BREAKER_CONSECUTIVE_LOSSES = 5         # Stop after 5 losses
```

---

## Order Execution Summary

### Paper Trading Order Flow
```
place_order(paper_mode=True)
  ↓
order_id = f"PAPER-{timestamp}"
  ↓
Fetch current LTP (for accuracy)
  ↓
Store in _paper_orders dict
  ↓
wait_for_order_completion() → Return True (instant)
  ↓
Trade created & saved to database
```

### Live Trading Order Flow
```
place_order(paper_mode=False)
  ↓
FOR attempt in 3 retries:
  ↓
  Build order parameters
  ↓
  Call kite.place_order() (ZERODHA API)
  ↓
  IF success: Return real order_id
  IF failure: Sleep 1 sec, retry
  ↓
wait_for_order_completion()
  ↓
Poll exchange every 2 seconds (max 30 sec)
  ↓
Check status: COMPLETE/REJECTED/CANCELLED
  ↓
Return True/False
```

---

## Position Tracking (Same for Both Modes)

All positions tracked in:
1. **Memory**: `self.active_trades` dictionary
2. **Database**: SQLite `trades` table
3. **Monitoring**: TradingBot.monitor_active_trades()

**Exit conditions** (identical in both modes):
- Stop Loss hit → exit_trade()
- Target hit → exit_trade()
- Trailing SL triggered → update SL & monitor
- Time exit → force close at FORCE_EXIT_TIME
- Emergency command → force_exit_all_positions()

---

## Charges & Fees Calculation

**Both modes calculate real charges:**

For a ₹250,000 LONG trade (100 qty × ₹2500):
- Brokerage: ₹40.00
- STT: ₹63.76
- Transaction: ₹16.41
- GST: ₹10.13
- SEBI: ₹5.05
- Stamp Duty: ₹7.50
- **Total: ₹142.85**

**Formula**: `calculate_charges()` in trading_bot.py (lines 883-923)

---

## Database Schema

**Key table**: `trades`

```sql
CREATE TABLE trades (
    id INTEGER PRIMARY KEY,
    trade_date DATE,
    symbol TEXT,
    direction TEXT,        -- LONG or SHORT
    quantity INTEGER,
    entry_time TIMESTAMP,
    entry_price REAL,
    stop_loss REAL,
    target_price REAL,
    exit_time TIMESTAMP,
    exit_price REAL,
    exit_reason TEXT,
    pnl REAL,             -- Net P&L after charges
    pnl_percent REAL,
    status TEXT,          -- OPEN or CLOSED
    order_id_entry TEXT,  -- PAPER-xxx or real ID
    order_id_exit TEXT
)
```

**Database location**: `data/trades.db` (SQLite)

---

## Emergency Commands

Available at runtime (both modes):

```
status          - Show current bot status
stop SYMBOL     - Stop monitoring a stock
resume SYMBOL   - Resume monitoring
list            - Show stopped stocks
emergency       - EMERGENCY STOP (exit all, halt trading)
exit            - Graceful shutdown
help            - Show all commands
```

---

## API Retry Logic (Live Mode Only)

```python
API_RETRY_COUNT = 3           # Try up to 3 times
API_RETRY_DELAY = 1.0         # Wait 1 second between retries
ORDER_TIMEOUT_SECONDS = 30    # Wait up to 30 seconds for completion
ORDER_STATUS_CHECK_INTERVAL = 2  # Check status every 2 seconds
```

**Retry Flow**:
1. Try API call
2. If fails: Sleep 1 second
3. Retry (max 3 total attempts)
4. If all fail: Return None

---

## Testing Checklist

### Before Going Live
- [ ] Run paper trading for 5-10 days
- [ ] Verify circuit breaker triggers correctly
- [ ] Test emergency stop command
- [ ] Validate database records
- [ ] Check P&L calculations
- [ ] Review charges/fees breakdown
- [ ] Verify trading hours logic
- [ ] Test position sizing

### Go-Live Requirements
- [ ] Zerodha credentials correctly set in .env
- [ ] API key and access token valid
- [ ] Sufficient capital in account
- [ ] Review all risk parameters in config.py
- [ ] Test with SMALL capital first
- [ ] Have emergency command ready
- [ ] Monitor first trade carefully
- [ ] Keep terminal open during trading hours

---

## How Modes Differ in Three Aspects

### 1. Order Execution
- **Paper**: In-memory dict, instant completion
- **Live**: Zerodha API, with retries & status polling

### 2. Capital Impact
- **Paper**: Simulated (P&L calculated, not real)
- **Live**: Real (charges deducted from account)

### 3. Risk
- **Paper**: None (learning/testing)
- **Live**: Real capital at stake

**Everything else is IDENTICAL**: Strategy logic, risk management, position tracking, exit conditions.

---

## Quick Troubleshooting

| Issue | Solution |
|-------|----------|
| Paper trades don't execute | Check: calculate_position_size() returns > 0 |
| Live trades timeout | Increase ORDER_TIMEOUT_SECONDS in config.py |
| Capital not updating | Check: exit_trade() is called, P&L is calculated |
| Orders rejected | Verify: Stock price > MIN_STOCK_PRICE, API is working |
| Circuit breaker triggers early | Check: MAX_DAILY_LOSS_PERCENT, CIRCUIT_BREAKER_LOSS_THRESHOLD |
| Can't place more trades | Check: MAX_DAILY_TRADES, MAX_OPEN_POSITIONS limits |

---

## Files to Understand

**If you have 10 minutes:**
- Read: PAPER_VS_LIVE_TRADING.md (Sections 1-3)
- Skim: ARCHITECTURE_SUMMARY.md

**If you have 1 hour:**
- Read: PAPER_VS_LIVE_TRADING.md (all sections)
- Study: ARCHITECTURE_SUMMARY.md diagrams
- Review: config.py (risk settings)

**If you have 2+ hours:**
- Read all documentation
- Review trading_bot.py (OrderManager class)
- Study database.py schema
- Run paper trading & review logs
- Check database records (data/trades.db)

---

## File Absolute Paths

- **Primary Config**: `/home/user/zerobot/config.py`
- **Main Bot**: `/home/user/zerobot/trading_bot.py`
- **Database**: `/home/user/zerobot/database.py`
- **Documentation**: `/home/user/zerobot/PAPER_VS_LIVE_TRADING.md`
- **Architecture**: `/home/user/zerobot/ARCHITECTURE_SUMMARY.md`
- **Database File**: `/home/user/zerobot/data/trades.db`
- **Logs**: `/home/user/zerobot/logs/trading_bot.log`

---

## Key Code Locations Summary

| What | File | Lines |
|------|------|-------|
| Mode Toggle | config.py | 77 |
| Paper Orders | trading_bot.py | 179-206 |
| Live Orders | trading_bot.py | 207-239 |
| Order Status | trading_bot.py | 241-281 |
| Trade Class | trading_bot.py | 90-155 |
| Trade Entry | trading_bot.py | 770-881 |
| Trade Exit | trading_bot.py | 925-1021 |
| Position Size | trading_bot.py | 737-757 |
| Circuit Breaker | trading_bot.py | 300-350 |
| Monitoring | trading_bot.py | 1023-1099 |
| Risk Config | config.py | 14-26, 76-88 |
| Database | database.py | 86-244 |
| Commands | command_handler.py | All |

---

## Next Steps

1. **Read** `PAPER_VS_LIVE_TRADING.md` (detailed analysis)
2. **Review** config.py (understand settings)
3. **Test** paper trading mode
4. **Verify** database records in data/trades.db
5. **Check** logs in logs/trading_bot.log
6. **Only then** switch to live mode with caution

Good luck!
