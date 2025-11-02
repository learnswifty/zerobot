# Zerobot Architecture Summary - Paper vs Live Trading

## System Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         TRADING BOT SYSTEM                              │
└─────────────────────────────────────────────────────────────────────────┘

                    ┌─────────────────────────────────┐
                    │    Configuration (config.py)    │
                    │  ENABLE_PAPER_TRADING = True    │
                    └────────────┬────────────────────┘
                                 │
                    ┌────────────▼──────────────┐
                    │   TradingBot (main)       │
                    │  - Initialize bot         │
                    │  - Load strategy          │
                    │  - Route to backtest/live │
                    └────────────┬──────────────┘
                                 │
                ┌────────────────┼────────────────┐
                │                │                │
        ┌───────▼────────┐   ┌────▼──────────┐   ┌──────▼─────────┐
        │  OrderManager  │   │ CircuitBreaker│   │ CommandHandler │
        │  (CRITICAL)    │   │   (Risk Mgmt) │   │   (Runtime)    │
        └───────┬────────┘   └───────────────┘   └────────────────┘
                │
        ┌───────┴────────────────────────┐
        │                                │
        │      MODE SELECTION            │
        │                                │
   ┌────▼──────────────────┐  ┌────────▼──────────────┐
   │  PAPER TRADING MODE    │  │  LIVE TRADING MODE    │
   │  (paper_mode = True)   │  │  (paper_mode = False) │
   └────┬──────────────────┘  └────────┬───────────────┘
        │                              │
   ┌────▼────────────────────┐  ┌──────▼──────────────────┐
   │  SIMULATED EXECUTION    │  │  REAL API EXECUTION    │
   │  1. Create PAPER-xxxxx  │  │  1. Build order params │
   │  2. Fetch current LTP   │  │  2. Call Zerodha API   │
   │  3. Mark COMPLETE       │  │  3. Get real order_id  │
   │  4. Store in memory     │  │  4. Retry (3 attempts) │
   │  5. Return immediately  │  │  5. Poll for status    │
   │                         │  │                        │
   │  No real money          │  │  Real capital at risk  │
   └────┬────────────────────┘  └──────┬─────────────────┘
        │                              │
        └──────────┬───────────────────┘
                   │
        ┌──────────▼──────────────┐
        │  Trade Object (Trade)   │
        │  - entry_price          │
        │  - entry_time           │
        │  - stop_loss            │
        │  - direction (LONG/SHORT)
        │  - quantity             │
        │  - pnl, pnl_percent     │
        │  - order_id_entry/exit  │
        └──────────┬──────────────┘
                   │
        ┌──────────▼──────────────────┐
        │  Database Persistence       │
        │  (database.py - SQLite)     │
        │  - Save trade entry         │
        │  - Update SL/Exit           │
        │  - Calculate daily stats    │
        │  - Track performance        │
        └─────────────────────────────┘
```

---

## Paper Trading Detailed Flow

```
┌──────────────────────────────────────────────────────────────┐
│              PAPER TRADING EXECUTION FLOW                    │
└──────────────────────────────────────────────────────────────┘

User selects "Paper Trading"
    │
    └─→ ENABLE_PAPER_TRADING = True
        │
        └─→ OrderManager.__init__(paper_mode=True)
            │
            └─→ _paper_orders = {}  (empty dictionary)
                │
                └─→ TradingBot.enter_trade(symbol, direction, entry_price, sl, qty)
                    │
                    └─→ order_manager.place_order(...)
                        │
                        IF paper_mode == True:
                        │
                        ├─→ order_id = f"PAPER-{timestamp}"
                        │
                        ├─→ IF price is None:
                        │   └─→ Fetch current LTP from Zerodha API
                        │       (Real price for accuracy)
                        │
                        ├─→ Store in _paper_orders dict:
                        │   {
                        │    'order_id': 'PAPER-1234567890',
                        │    'status': 'COMPLETE',
                        │    'tradingsymbol': 'RELIANCE',
                        │    'transaction_type': 'BUY',
                        │    'quantity': 100,
                        │    'price': 2500.50,
                        │    'average_price': 2500.50
                        │   }
                        │
                        └─→ Return 'PAPER-1234567890'
                            │
                            └─→ order_manager.wait_for_order_completion(order_id)
                                │
                                IF paper_mode == True:
                                │
                                └─→ RETURN True immediately
                                    (No wait needed - already complete)
                                    │
                                    └─→ Trade object created
                                        │
                                        └─→ Save to database
                                            │
                                            └─→ Capital updated
                                                (P&L = exit_price - entry_price)
                                                MINUS calculated charges
```

---

## Live Trading Detailed Flow

```
┌──────────────────────────────────────────────────────────────┐
│              LIVE TRADING EXECUTION FLOW                     │
└──────────────────────────────────────────────────────────────┘

User selects "Live Trading" (requires "CONFIRM")
    │
    └─→ ENABLE_PAPER_TRADING = False
        │
        └─→ OrderManager.__init__(paper_mode=False)
            │
            └─→ TradingBot.enter_trade(symbol, direction, entry_price, sl, qty)
                │
                └─→ order_manager.place_order(...)
                    │
                    IF paper_mode == False:
                    │
                    RETRY LOOP (up to 3 attempts):
                    │
                    ├─→ Build order_params:
                    │   {
                    │    'tradingsymbol': 'RELIANCE',
                    │    'exchange': 'NSE',
                    │    'transaction_type': 'BUY',
                    │    'quantity': 100,
                    │    'order_type': 'MARKET',
                    │    'product': 'MIS',
                    │    'validity': 'DAY'
                    │   }
                    │
                    ├─→ CALL ZERODHA API:
                    │   kite.place_order(variety=VARIETY_REGULAR, **order_params)
                    │
                    ├─→ Get real order_id from exchange
                    │   (e.g., '123456789')
                    │
                    ├─→ IF success: RETURN order_id
                    │
                    └─→ IF failure & attempts < 3:
                        │
                        └─→ Sleep 1 second (API_RETRY_DELAY)
                            │
                            └─→ RETRY (goto RETRY LOOP)
                                │
                                └─→ order_manager.wait_for_order_completion(order_id)
                                    │
                                    POLL EXCHANGE (every 2 seconds, max 30 sec):
                                    │
                                    ├─→ kite.orders()  (Fetch all orders)
                                    │
                                    ├─→ Find order by order_id
                                    │
                                    ├─→ Check status:
                                    │   - COMPLETE → RETURN True
                                    │   - REJECTED → RETURN False
                                    │   - CANCELLED → RETURN False
                                    │   - OPEN → SLEEP & RETRY
                                    │
                                    └─→ TIMEOUT (30s) → RETURN False
                                        │
                                        └─→ IF True:
                                            └─→ Trade object created
                                                │
                                                └─→ Save to database
                                                    │
                                                    └─→ Capital updated
                                                        (Real execution price)
                                                        MINUS real charges
                                                        (Deducted from account)
```

---

## Order Manager State Management

```
┌────────────────────────────────────────────────────────┐
│          OrderManager State Variables                   │
└────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│    Paper Mode (ENABLE_PAPER_TRADING=True)   │
├─────────────────────────────────────────────┤
│ self.paper_mode = True                      │
│ self._paper_orders = {                      │
│   'PAPER-1234567890': {                    │
│     'order_id': 'PAPER-1234567890',        │
│     'status': 'COMPLETE',                  │
│     'tradingsymbol': 'RELIANCE',           │
│     'quantity': 100,                       │
│     'average_price': 2500.50               │
│   },                                       │
│   'PAPER-1234567891': { ... }              │
│ }                                           │
│ self.kite = KiteConnect (authenticated)    │
│           (only used to fetch prices)      │
└─────────────────────────────────────────────┘

┌─────────────────────────────────────────────┐
│   Live Mode (ENABLE_PAPER_TRADING=False)    │
├─────────────────────────────────────────────┤
│ self.paper_mode = False                     │
│ self._paper_orders = {}  (not used)         │
│ self.kite = KiteConnect (authenticated)     │
│           (used for ALL operations)         │
│ self.retry_count = 3 (TradingConfig)       │
│ self.retry_delay = 1.0 sec (TradingConfig) │
└─────────────────────────────────────────────┘
```

---

## Position Tracking (Identical in Both Modes)

```
┌────────────────────────────────────────────────────────┐
│          Unified Position Tracking                      │
│      (SAME for Paper and Live Trading)                 │
└────────────────────────────────────────────────────────┘

Active Trades Dictionary:
    self.active_trades = {
        'RELIANCE': Trade(
            symbol='RELIANCE',
            direction='LONG',
            entry_time=2025-11-02 10:30:00,
            entry_price=2500.50,
            quantity=100,
            stop_loss=2450.00,
            target_price=2600.00,
            pnl=0.0,
            max_favorable_excursion=0.0,
            max_adverse_excursion=0.0,
            status='OPEN',
            order_id_entry='PAPER-xxx' or '123456789'
        ),
        'TCS': Trade(...),
    }

Database Persistence (SQLite):
    trades table:
        trade_id=1, trade_date='2025-11-02', symbol='RELIANCE'
        direction='LONG', quantity=100
        entry_time=..., entry_price=2500.50
        stop_loss=2450.00, initial_stop_loss=2450.00
        target_price=2600.00
        exit_time=NULL, exit_price=NULL (if still open)
        status='OPEN'
        order_id_entry='PAPER-xxx' or '123456789'
        order_id_exit=NULL

Monitoring Loop (Same Logic):
    while is_running:
        for symbol, trade in active_trades.items():
            ltp = fetch_quote(symbol)
            trade.update_excursions(ltp)
            
            if ltp <= trade.stop_loss:
                exit_trade(trade, ltp, 'STOP_LOSS')
            elif ltp >= trade.target_price:
                exit_trade(trade, ltp, 'TARGET')
            elif use_trailing_sl:
                trade.update_trailing_stop(ltp, trailing_percent)
```

---

## Configuration Control Points

```
┌──────────────────────────────────────────────────────┐
│         Key Configuration Parameters                 │
│          (All in config.py)                          │
└──────────────────────────────────────────────────────┘

MODE SELECTION:
  ENABLE_PAPER_TRADING = True/False
  ↓
  Controls OrderManager.paper_mode
  ↓
  IF True:  paper_mode_orders()
  IF False: live_mode_orders_with_retries()

RISK MANAGEMENT:
  MAX_OPEN_POSITIONS = 5
  MAX_DAILY_TRADES = 10
  MAX_ENTRIES_PER_STOCK = 2
  MAX_STOP_LOSS_PERCENT = 5.0
  MIN_STOP_LOSS_PERCENT = 0.5
  
  CIRCUIT_BREAKER_ENABLED = True
  CIRCUIT_BREAKER_LOSS_THRESHOLD = 1500 INR
  CIRCUIT_BREAKER_CONSECUTIVE_LOSSES = 5
  MAX_DAILY_LOSS_PERCENT = 5.0

ORDER SETTINGS (Live Mode Only):
  ORDER_TYPE_DEFAULT = 'MARKET'
  ORDER_PRODUCT_TYPE = 'MIS' (intraday)
  ORDER_VALIDITY = 'DAY'
  ORDER_TIMEOUT_SECONDS = 30
  ORDER_STATUS_CHECK_INTERVAL = 2
  API_RETRY_COUNT = 3
  API_RETRY_DELAY = 1.0

CAPITAL SETTINGS:
  DEFAULT_CAPITAL = 10000
  DEFAULT_LEVERAGE = 5.0
  (Buying Power = 10000 * 5 = 50000)

TRADING HOURS:
  MARKET_OPEN_TIME = 9:15
  MARKET_CLOSE_TIME = 15:30
  TRADING_END_TIME = 14:55 (stop new entries)
  FORCE_EXIT_TIME = 15:15 (force close all)
```

---

## Key Implementation Details

### Paper Mode Order ID Generation
```python
order_id = f"PAPER-{int(time.time() * 1000)}"

Example outputs:
  PAPER-1730520600000  (ms timestamp)
  PAPER-1730520600123
  PAPER-1730520600456

These are ALWAYS unique and never conflict with real Zerodha order IDs
(which are numeric or alphanumeric without PAPER- prefix)
```

### Live Mode Retry Logic
```python
for attempt in range(3):  # max 3 attempts
    try:
        order_id = kite.place_order(...)
        return order_id  # Success
    except Exception as e:
        if attempt < 2:  # Not last attempt
            sleep(1)     # Wait 1 second
        else:            # Last attempt
            return None  # Failed
```

### Exit Charge Calculation
```
For a LONG trade:
  - Buy Value = 2500.50 * 100 = 250,050
  - Sell Value = 2550.50 * 100 = 255,050
  - Turnover = 505,100

Charges breakdown:
  1. Brokerage = min(250,050 * 0.0003, 20) + min(255,050 * 0.0003, 20) = 20 + 20 = 40
  2. STT = 255,050 * 0.00025 = 63.76
  3. Transaction = 505,100 * 0.0000325 = 16.41
  4. GST = (40 + 16.41) * 0.18 = 10.13
  5. SEBI = 505,100 * 0.00001 = 5.05
  6. Stamp Duty = 250,050 * 0.00003 = 7.50
  
  Total = 40 + 63.76 + 16.41 + 10.13 + 5.05 + 7.50 = 142.85

Gross P&L = (2550.50 - 2500.50) * 100 = 5,000
Net P&L = 5,000 - 142.85 = 4,857.15
```

---

## Safety Features Comparison

| Feature | Paper | Live |
|---------|-------|------|
| **Default** | Enabled | Disabled |
| **Requires Confirmation** | Optional | YES |
| **Circuit Breaker** | YES | YES |
| **Emergency Stop** | YES | YES |
| **Daily Loss Limit** | Applies | Applies |
| **Max Positions** | Enforced | Enforced |
| **Trading Hours Check** | Enforced | Enforced |
| **Real Money** | NO | YES |
| **Order Confirmation** | Can skip | Can require |
| **API Retries** | N/A | 3 attempts |

---

## Common Issues and Solutions

### Paper Mode Always Succeeds
```
Why: All orders instantly complete
Solution: This is by design for testing

To simulate failures in paper mode:
- Modify calculate_position_size() to return 0
- Modify enter_trade() to return None
```

### Live Mode Order Timeout
```
Why: Exchange not responding or order taking >30 seconds
Solution: 
  - Increase ORDER_TIMEOUT_SECONDS in config.py
  - Check internet connection
  - Verify market is open
  - Try again during market hours
```

### Capital Not Updating
```
Paper: Check database is being written
       Verify exit_trade() is being called
       Check P&L calculation

Live: Check broker balance in Zerodha terminal
      Verify order was actually executed
      Confirm exit price is correct
```

---

## For Transition from Paper to Live

1. **Same Strategy Logic**: Code path is identical
   - Entry conditions: same
   - Exit conditions: same  
   - Risk management: same
   - Position sizing: same

2. **Only Difference**: How orders are executed
   - Paper: Simulated in memory
   - Live: Real API calls

3. **Test Checklist**:
   - Run paper trading for 5-10 days minimum
   - Verify circuit breaker triggers correctly
   - Test emergency stop command
   - Check database records
   - Validate P&L calculations
   - Review charges/fees breakdown

4. **Go-Live Checklist**:
   - Verify credentials (API key, access token)
   - Start with SMALL capital
   - Monitor FIRST trade carefully
   - Have emergency command ready
   - Keep terminal open (watch for unexpected behavior)

