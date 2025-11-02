# Paper Trading vs Live Trading Analysis - Zerobot

## Executive Summary
The codebase implements a unified trading system that can operate in either **Paper Trading Mode** (simulated) or **Live Trading Mode** (real orders). The key difference is controlled by a single configuration flag that switches between simulated order execution and real Zerodha API calls.

---

## 1. WHERE PAPER TRADING LOGIC IS IMPLEMENTED

### Main Configuration (config.py - Line 77)
```python
ENABLE_PAPER_TRADING = True  # True = Paper trading, False = Live trading
```

### OrderManager Class (trading_bot.py - Lines 157-298)
The `OrderManager` class handles both paper and live trading through conditional logic:

**Paper Mode Orders (Lines 179-206):**
```python
if self.paper_mode:
    order_id = f"PAPER-{int(time.time() * 1000)}"
    # Simulated execution - no API call
    actual_price = price
    if actual_price is None and order_type == 'MARKET':
        try:
            quote = self.kite.quote(f"{TradingConfig.DEFAULT_EXCHANGE}:{symbol}")
            actual_price = quote[f"{TradingConfig.DEFAULT_EXCHANGE}:{symbol}"]['last_price']
        except:
            actual_price = 0.0
    
    self._paper_orders[order_id] = {
        'order_id': order_id,
        'status': 'COMPLETE',
        'tradingsymbol': symbol,
        'transaction_type': transaction_type,
        'quantity': quantity,
        'price': actual_price,
        'average_price': actual_price
    }
    self.logger.info(f"[PAPER] Simulated order {order_id} | {symbol} | {transaction_type} {quantity} @ {price_str}")
    return order_id
```

**Key Characteristics of Paper Mode:**
- Orders are created with "PAPER-" prefix
- No actual order is placed on the exchange
- Orders are instantly marked as COMPLETE
- Simulated prices are used (fetched from API for accuracy)
- In-memory dictionary (`_paper_orders`) tracks all paper orders

### Paper Mode Order Status (Lines 241-245)
```python
def get_order_status(self, order_id: str) -> Optional[Dict]:
    # Paper mode: instantly complete
    if self.paper_mode:
        return self._paper_orders.get(order_id, {'order_id': order_id, 'status': 'COMPLETE'})
```

### Paper Mode Order Completion (Lines 261-265)
```python
def wait_for_order_completion(self, order_id: str, timeout: int = 30) -> bool:
    # Paper mode: orders are immediately complete
    if self.paper_mode:
        return True
```

### Paper Mode Order Cancellation (Lines 283-290)
```python
def cancel_order(self, order_id: str) -> bool:
    if self.paper_mode:
        if order_id in self._paper_orders:
            self._paper_orders[order_id]['status'] = 'CANCELLED'
        self.logger.info(f"[PAPER] Order {order_id} cancelled")
        return True
```

---

## 2. WHERE LIVE TRADING LOGIC IS IMPLEMENTED

### Live Mode Orders (Lines 207-239)
The code falls through to live trading when `self.paper_mode` is False:

```python
for attempt in range(self.retry_count):
    try:
        order_params = {
            'tradingsymbol': symbol,
            'exchange': TradingConfig.DEFAULT_EXCHANGE,
            'transaction_type': transaction_type,
            'quantity': quantity,
            'order_type': order_type,
            'product': TradingConfig.ORDER_PRODUCT_TYPE,
            'validity': TradingConfig.ORDER_VALIDITY
        }

        if price and order_type == 'LIMIT':
            order_params['price'] = price

        if trigger_price:
            order_params['trigger_price'] = trigger_price

        # ACTUAL ORDER PLACEMENT VIA ZERODHA API
        order_id = self.kite.place_order(variety=self.kite.VARIETY_REGULAR, **order_params)

        self.logger.order_placed(order_id, symbol, transaction_type, quantity, price)
        return order_id

    except Exception as e:
        self.logger.error(f"Order placement attempt {attempt + 1} failed: {str(e)}")
        if attempt < self.retry_count - 1:
            time.sleep(self.retry_delay)
        else:
            self.logger.order_failed(symbol, str(e))
            return None
```

**Key Characteristics of Live Mode:**
- Direct API calls to Zerodha KiteConnect (`self.kite.place_order()`)
- Retry logic with configurable attempts (default: 3 tries)
- Retry delay between attempts (default: 1 second)
- Real order IDs from exchange
- Actual money is involved

### Live Mode Order Status (Lines 246-259)
```python
try:
    orders = self.kite.orders()
    for order in orders:
        if order['order_id'] == order_id:
            return order
    return None
except Exception as e:
    self.logger.error(f"Failed to get order status: {str(e)}")
    return None
```

### Live Mode Order Completion (Lines 266-281)
```python
while (time.time() - start_time) < timeout:
    status = self.get_order_status(order_id)

    if status:
        if status['status'] == 'COMPLETE':
            return True
        elif status['status'] in ['REJECTED', 'CANCELLED']:
            self.logger.error(f"Order {order_id} {status['status']}")
            return False

    time.sleep(TradingConfig.ORDER_STATUS_CHECK_INTERVAL)

self.logger.warning(f"Order {order_id} timeout after {timeout}s")
return False
```

---

## 3. KEY DIFFERENCES BETWEEN PAPER AND LIVE TRADING

| Aspect | Paper Trading | Live Trading |
|--------|---------------|--------------|
| **Order Placement** | Simulated in-memory | Real API call to Zerodha |
| **Order ID Format** | `PAPER-{timestamp}` | Zerodha order ID |
| **Execution Time** | Immediate | Depends on market/order type |
| **Price** | Current LTP fetched from API | Actual market execution price |
| **Order Status** | Always COMPLETE immediately | Polls exchange for real status |
| **Fees/Charges** | Simulated (calculated) | Real charges deducted |
| **Risk** | No real money at risk | Real capital at risk |
| **Capital Impact** | Simulated P&L | Real balance changes |
| **Retry Logic** | Not needed | Full retry mechanism (3 attempts) |
| **Cancellation** | Simple flag change | Real API cancel call |

---

## 4. CONFIGURATION FILES CONTROLLING PAPER vs LIVE MODE

### Primary Configuration File: `config.py`

**Line 77 - Trading Mode Toggle:**
```python
ENABLE_PAPER_TRADING = True      # True = Paper trading, False = Live trading
```

**Related Safety Settings (Lines 76-88):**
```python
# ==================== SAFETY SETTINGS ====================
ENABLE_PAPER_TRADING = True      # True = Paper trading, False = Live trading
REQUIRE_ORDER_CONFIRMATION = False # Ask user before placing orders (disable for automated trading)

# Circuit breaker - Automatic trading halt on excessive losses
ENABLE_CIRCUIT_BREAKER = True
CIRCUIT_BREAKER_LOSS_THRESHOLD = 1500
CIRCUIT_BREAKER_CONSECUTIVE_LOSSES = 5

# Emergency stop
EMERGENCY_STOP_ENABLED = True
```

**Risk Management Configuration (Lines 14-26):**
```python
# Capital & Risk Management
DEFAULT_CAPITAL = 10000
DEFAULT_LEVERAGE = 5.0
MAX_POSITION_SIZE_PERCENT = 100
MIN_POSITION_SIZE = 1
MAX_DAILY_LOSS_PERCENT = 5.0
MAX_DAILY_TRADES = 10
MAX_ENTRIES_PER_STOCK = 2
MAX_OPEN_POSITIONS = 5
MAX_STOP_LOSS_PERCENT = 5.0
MIN_STOP_LOSS_PERCENT = 0.5
```

**Order Settings (Lines 64-75):**
```python
ORDER_TYPE_DEFAULT = 'MARKET'    # MARKET or LIMIT
ORDER_PRODUCT_TYPE = 'MIS'       # MIS (intraday) or CNC (delivery)
ORDER_VALIDITY = 'DAY'           # DAY or IOC
ORDER_TIMEOUT_SECONDS = 30       # Timeout for order placement
ORDER_STATUS_CHECK_INTERVAL = 2  # Check order status every N seconds
```

### Runtime Mode Selection: `trading_bot.py` (Lines 1670-1696)

```python
def get_trading_mode() -> bool:
    """Ask user for paper trading or live trading mode"""
    print_header("Trading Mode Selection")
    print(f"{Colors.BOLD}Choose trading mode:{Colors.ENDC}\n")
    print(f"  {Colors.OKGREEN}1. Paper Trading{Colors.ENDC} - Simulated orders")
    print(f"  {Colors.FAIL}2. Live Trading{Colors.ENDC}  - Real orders with real money")
    
    while True:
        choice = input(f"{Colors.BOLD}Enter choice (1/2) [default: 1]: {Colors.ENDC}").strip()
        
        if not choice or choice == '1':
            return True  # Paper trading
        elif choice == '2':
            # Live trading requires explicit confirmation
            confirm = input(f"\n{Colors.BOLD}Type 'CONFIRM' to proceed: {Colors.ENDC}").strip()
            if confirm == 'CONFIRM':
                return False  # Live trading
```

### Mode Update at Runtime (Lines 1838-1841):

```python
# Step 1: Ask for trading mode (paper or live)
is_paper_trading = get_trading_mode()

# Update config based on user selection
TradingConfig.ENABLE_PAPER_TRADING = is_paper_trading
```

---

## 5. HOW ORDERS ARE EXECUTED IN EACH MODE

### Paper Trading Order Execution Flow

```
enter_trade() → order_manager.place_order()
    ↓
Check if paper_mode == True
    ↓
Create simulated order with:
  - order_id = PAPER-{timestamp}
  - status = COMPLETE (immediate)
  - Fetch current LTP from API (for accuracy)
  - Store in _paper_orders dict
    ↓
order_manager.wait_for_order_completion()
    ↓
Return True immediately (already complete)
    ↓
Trade object created and saved to database
    ↓
Capital updated based on simulated P&L
```

**Example Paper Order Creation (Lines 180-206):**
```python
if self.paper_mode:
    order_id = f"PAPER-{int(time.time() * 1000)}"
    actual_price = price or fetch_current_ltp()
    
    self._paper_orders[order_id] = {
        'order_id': order_id,
        'status': 'COMPLETE',
        'tradingsymbol': symbol,
        'transaction_type': transaction_type,
        'quantity': quantity,
        'average_price': actual_price
    }
    return order_id
```

### Live Trading Order Execution Flow

```
enter_trade() → order_manager.place_order()
    ↓
Check if paper_mode == False
    ↓
Retry loop (up to 3 attempts):
  - Build order_params dict
  - Call self.kite.place_order() (REAL API CALL)
  - Return real order_id on success
  - Retry with 1 second delay on failure
    ↓
order_manager.wait_for_order_completion()
    ↓
Poll exchange status every 2 seconds (up to 30 second timeout):
  - Fetch orders from exchange
  - Check order status (COMPLETE, REJECTED, CANCELLED)
  - Return success/failure
    ↓
If successful:
  - Trade object created and saved to database
  - Real capital/buying_power updated with actual execution price
```

**Example Live Order Placement (Lines 208-230):**
```python
for attempt in range(self.retry_count):  # 3 attempts
    try:
        order_params = {
            'tradingsymbol': symbol,
            'exchange': TradingConfig.DEFAULT_EXCHANGE,
            'transaction_type': transaction_type,
            'quantity': quantity,
            'order_type': order_type,
            'product': TradingConfig.ORDER_PRODUCT_TYPE,
            'validity': TradingConfig.ORDER_VALIDITY
        }
        
        # REAL API CALL TO ZERODHA
        order_id = self.kite.place_order(variety=self.kite.VARIETY_REGULAR, **order_params)
        
        self.logger.order_placed(order_id, symbol, transaction_type, quantity, price)
        return order_id
        
    except Exception as e:
        if attempt < self.retry_count - 1:
            time.sleep(self.retry_delay)  # Wait 1 second before retry
        else:
            self.logger.order_failed(symbol, str(e))
            return None
```

---

## 6. HOW POSITIONS ARE TRACKED IN EACH MODE

### Unified Position Tracking (Both Modes)

The position tracking is **identical** for both modes:

**Trade Object (Lines 90-155):**
```python
class Trade:
    def __init__(self, symbol: str, direction: str, entry_time: datetime,
                 entry_price: float, quantity: int, stop_loss: float,
                 target_price: float = None, trade_id: int = None):
        self.trade_id = trade_id
        self.symbol = symbol
        self.direction = direction  # LONG or SHORT
        self.entry_time = entry_time
        self.entry_price = entry_price
        self.quantity = quantity
        self.stop_loss = stop_loss
        self.initial_stop_loss = stop_loss
        self.target_price = target_price
        self.exit_time = None
        self.exit_price = None
        self.exit_reason = None
        self.pnl = 0.0
        self.pnl_percent = 0.0
        self.max_favorable_excursion = 0.0
        self.max_adverse_excursion = 0.0
        self.status = 'OPEN'
        self.order_id_entry = None
        self.order_id_exit = None
```

**Active Trades Dictionary (Line 398):**
```python
self.active_trades: Dict[str, Trade] = {}  # Keys are symbols, values are Trade objects
```

### Database Persistence (database.py)

Both modes save trades to SQLite database:

**Trades Table Schema (Lines 92-118):**
```python
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
```

### Position Monitoring (Lines 1023-1099)

Both modes use same monitoring logic:

```python
def monitor_active_trades(self):
    """Monitor and manage active trades"""
    if not self.active_trades:
        return
    
    # Get quotes for all active stocks
    symbols = list(self.active_trades.keys())
    quotes = self.kite.quote([f"{TradingConfig.DEFAULT_EXCHANGE}:{s}" for s in symbols])
    
    for symbol, trade in list(self.active_trades.items()):
        quote = quotes[f"{TradingConfig.DEFAULT_EXCHANGE}:{symbol}"]
        ltp = quote['last_price']
        
        # Update excursions (same for both modes)
        trade.update_excursions(ltp)
        
        # Check stop loss (same logic)
        if self._check_stop_loss(ltp, trade):
            self.exit_trade(trade, ltp, 'STOP_LOSS')
            continue
        
        # Check target (same logic)
        if self.exit_strategy.use_rr and self._check_target(ltp, trade):
            self.exit_trade(trade, ltp, 'TARGET')
            continue
        
        # Update trailing stop (same logic)
        if self.exit_strategy.use_trailing_sl:
            trade.update_trailing_stop(ltp, self.exit_strategy.trailing_sl_percent)
```

### Key Difference in Position Tracking

**Paper Mode:**
- Positions are tracked in memory and database
- Simulated prices used for monitoring
- No actual broker position

**Live Mode:**
- Positions tracked in memory and database
- Real market prices used for monitoring
- MUST match actual broker positions

---

## 7. RISK MANAGEMENT DIFFERENCES

### Shared Risk Management (Both Modes)

The risk management is **identical** for both paper and live trading:

#### A. Position Sizing (Lines 737-757)

```python
def calculate_position_size(self, price: float) -> int:
    """Calculate position size based on buying power"""
    if price <= 0:
        self.logger.error(f"Invalid price for position sizing: {price}")
        return 0
    
    max_quantity = int(self.buying_power / price)
    
    if max_quantity < TradingConfig.MIN_POSITION_SIZE:
        self.logger.warning(f"Insufficient buying power")
        return 0
    
    # Apply maximum position size limit
    max_allowed = getattr(TradingConfig, 'MAX_POSITION_SIZE', None)
    if max_allowed and max_quantity > max_allowed:
        max_quantity = max_allowed
    
    return max_quantity
```

**Configuration Settings (config.py):**
```python
MAX_POSITION_SIZE_PERCENT = 100  # % of buying power per trade
MIN_POSITION_SIZE = 1            # Minimum quantity
MAX_OPEN_POSITIONS = 5           # Maximum simultaneous positions
```

#### B. Stop Loss Validation (Lines 783-802)

```python
# Validate stop loss placement
if direction == 'LONG':
    if stop_loss >= entry_price:
        self.logger.error(f"Invalid SL for LONG: SL {stop_loss} must be < Entry {entry_price}")
        return None
    sl_percent = ((entry_price - stop_loss) / entry_price) * 100
else:  # SHORT
    if stop_loss <= entry_price:
        self.logger.error(f"Invalid SL for SHORT: SL {stop_loss} must be > Entry {entry_price}")
        return None
    sl_percent = ((stop_loss - entry_price) / entry_price) * 100

# Validate stop loss percentage
if sl_percent < TradingConfig.MIN_STOP_LOSS_PERCENT:
    self.logger.error(f"Stop loss too tight: {sl_percent:.2f}%")
    return None

if sl_percent > TradingConfig.MAX_STOP_LOSS_PERCENT:
    self.logger.error(f"Stop loss too wide: {sl_percent:.2f}%")
    return None
```

**Configuration Settings:**
```python
MAX_STOP_LOSS_PERCENT = 5.0      # Maximum stop loss per trade
MIN_STOP_LOSS_PERCENT = 0.5      # Minimum stop loss per trade
```

#### C. Circuit Breaker (Lines 300-350)

Both modes use identical circuit breaker logic:

```python
class CircuitBreaker:
    def check(self, current_capital: float, initial_capital: float,
              consecutive_losses: int, trade_date: str) -> bool:
        
        if not self.enabled or self.triggered:
            return self.triggered
        
        # Check daily loss limit
        current_loss = initial_capital - current_capital
        max_loss = initial_capital * (TradingConfig.MAX_DAILY_LOSS_PERCENT / 100)
        
        if current_loss >= max_loss:
            self.trigger("Daily loss limit exceeded", current_loss)
            return True
        
        # Check absolute loss threshold
        if current_loss >= TradingConfig.CIRCUIT_BREAKER_LOSS_THRESHOLD:
            self.trigger("Absolute loss threshold exceeded", current_loss)
            return True
        
        # Check consecutive losses
        if consecutive_losses >= TradingConfig.CIRCUIT_BREAKER_CONSECUTIVE_LOSSES:
            self.trigger(f"{consecutive_losses} consecutive losses", current_loss)
            return True
        
        return False
```

**Configuration Settings:**
```python
ENABLE_CIRCUIT_BREAKER = True
CIRCUIT_BREAKER_LOSS_THRESHOLD = 1500  # Stop if loss exceeds ₹1500
CIRCUIT_BREAKER_CONSECUTIVE_LOSSES = 5  # Stop after N consecutive losses
MAX_DAILY_LOSS_PERCENT = 5.0
MAX_DAILY_TRADES = 10
MAX_ENTRIES_PER_STOCK = 2
```

#### D. Emergency Stop (Lines 388-391, 494-507)

Both modes support emergency stop via command interface:

```python
def handle_emergency_stop():
    # Set emergency stop flag
    self.emergency_stop_triggered = True
    self.logger.critical("Emergency stop triggered!")
    
    # Force exit all positions immediately
    self.force_exit_all_positions("EMERGENCY_STOP")
    
    # Halt all trading
    self.is_running = False
```

#### E. Trading Hours Restrictions (Lines 520-547)

```python
def can_take_new_position(self) -> bool:
    # Check emergency stop
    if self.emergency_stop_triggered:
        return False
    
    # Check trading hours
    now = datetime.now().time()
    if now > TradingConfig.TRADING_END_TIME:
        return False
    
    # Check daily trade limit
    if self.daily_trades_count >= TradingConfig.MAX_DAILY_TRADES:
        self.logger.warning(f"Daily trade limit reached")
        return False
    
    # Check open positions limit
    if len(self.active_trades) >= TradingConfig.MAX_OPEN_POSITIONS:
        self.logger.warning(f"Max open positions reached")
        return False
    
    # Check circuit breaker
    consecutive_losses = self.db.get_consecutive_losses(self.today_date)
    if self.circuit_breaker.check(self.current_capital, self.initial_capital,
                                 consecutive_losses, self.today_date):
        return False
    
    return True
```

**Configuration:**
```python
MARKET_OPEN_TIME = dt_time(9, 15)
MARKET_CLOSE_TIME = dt_time(15, 30)
TRADING_START_TIME = dt_time(9, 15)
TRADING_END_TIME = dt_time(14, 55)      # Stop taking new positions
FORCE_EXIT_TIME = dt_time(15, 15)       # Force exit all positions
```

### ONE KEY DIFFERENCE: Order Confirmation

**Paper Mode (Optional Confirmation):**
```python
if TradingConfig.REQUIRE_ORDER_CONFIRMATION and not TradingConfig.ENABLE_PAPER_TRADING:
    # Only requires confirmation in LIVE mode
```

This means:
- **Paper Trading**: Can skip confirmation (for testing)
- **Live Trading**: Can require user confirmation before real orders

---

## 8. CHARGES AND FEES CALCULATION

Both modes calculate real charges:

**Charges Calculation (Lines 883-923):**
```python
def calculate_charges(self, entry_price: float, exit_price: float, 
                     quantity: int, direction: str) -> Dict[str, float]:
    
    # Turnover calculation
    buy_value = entry_price * quantity if direction == 'LONG' else exit_price * quantity
    sell_value = exit_price * quantity if direction == 'LONG' else entry_price * quantity
    turnover = buy_value + sell_value
    
    # 1. Brokerage (₹20 per order max or 0.03%)
    brokerage_buy = min(buy_value * 0.0003, 20)
    brokerage_sell = min(sell_value * 0.0003, 20)
    total_brokerage = brokerage_buy + brokerage_sell
    
    # 2. STT (0.025% on sell side for intraday equity)
    stt = sell_value * 0.00025
    
    # 3. Transaction charges (NSE: 0.00325% on turnover)
    transaction_charges = turnover * 0.0000325
    
    # 4. GST (18% on brokerage + transaction charges)
    gst = (total_brokerage + transaction_charges) * 0.18
    
    # 5. SEBI charges (₹10 per crore)
    sebi_charges = turnover * 0.00001
    
    # 6. Stamp duty (0.003% on buy side)
    stamp_duty = buy_value * 0.00003
    
    # Total charges
    total_charges = total_brokerage + stt + transaction_charges + gst + sebi_charges + stamp_duty
    
    return {
        'brokerage': total_brokerage,
        'stt': stt,
        'transaction_charges': transaction_charges,
        'gst': gst,
        'sebi_charges': sebi_charges,
        'stamp_duty': stamp_duty,
        'total_charges': total_charges,
        'turnover': turnover
    }
```

**Example Output (Lines 950-989):**
```
P&L Breakdown:
  Gross P&L:           ₹150.00

Charges & Taxes:
  Brokerage:           ₹20.00
  STT:                 ₹0.10
  Transaction Charges: ₹0.33
  GST (18%):           ₹3.69
  SEBI Charges:        ₹0.07
  Stamp Duty:          ₹0.01
  Total Charges:       ₹24.20

Net P&L:               ₹125.80
```

---

## 9. DATA FLOW COMPARISON

### Paper Trading Flow
```
User selects "Paper Trading"
    ↓
set ENABLE_PAPER_TRADING = True
    ↓
OrderManager created with paper_mode = True
    ↓
enter_trade() → place_order(paper_mode=True)
    ↓
Simulated order created (PAPER-xxxx)
    ↓
Stored in memory (_paper_orders dict)
    ↓
Trade object created
    ↓
Saved to SQLite database
    ↓
Capital updated (simulated)
    ↓
Exit on SL/Target/Time (same logic)
    ↓
P&L calculated with real fees
    ↓
Database updated
    ↓
Database summary generated
```

### Live Trading Flow
```
User selects "Live Trading" (requires CONFIRM)
    ↓
set ENABLE_PAPER_TRADING = False
    ↓
OrderManager created with paper_mode = False
    ↓
enter_trade() → place_order(paper_mode=False)
    ↓
Order placed to Zerodha API (with retries)
    ↓
Real order_id received from exchange
    ↓
Trade object created
    ↓
Saved to SQLite database
    ↓
Capital updated (real execution price)
    ↓
Monitor active trades (real-time from API)
    ↓
Exit on SL/Target/Time (same logic)
    ↓
P&L calculated with real fees
    ↓
Real balance changes
    ↓
Database updated
    ↓
Database summary generated
```

---

## 10. FILE LOCATIONS SUMMARY

| Component | File | Lines | Purpose |
|-----------|------|-------|---------|
| **Configuration** | `config.py` | 1-215 | All trading parameters |
| **Main Bot Logic** | `trading_bot.py` | 1-1888 | Core trading engine |
| **Order Manager** | `trading_bot.py` | 157-298 | Order execution (paper/live) |
| **Trade Class** | `trading_bot.py` | 90-155 | Trade object definition |
| **Circuit Breaker** | `trading_bot.py` | 300-350 | Risk management |
| **Database** | `database.py` | 1-400+ | SQLite persistence |
| **Command Handler** | `command_handler.py` | 1-244 | Runtime bot control |
| **Logger** | `logger.py` | 1-300+ | Logging system |
| **Backtest Engine** | `intra_back_5_exit.py` | 1-1000+ | Historical backtesting |

---

## 11. QUICK REFERENCE: SWITCHING MODES

### Switch to Paper Trading
```python
# In config.py
ENABLE_PAPER_TRADING = True

# Or at runtime via user prompt
is_paper_trading = get_trading_mode()  # Select option 1
TradingConfig.ENABLE_PAPER_TRADING = True
```

### Switch to Live Trading
```python
# In config.py
ENABLE_PAPER_TRADING = False

# Or at runtime via user prompt
is_paper_trading = get_trading_mode()  # Select option 2, type CONFIRM
TradingConfig.ENABLE_PAPER_TRADING = False
```

### Safety Features
1. **Paper mode is default** (Line 77 in config.py)
2. **Live mode requires explicit confirmation** (Lines 1684-1693 in trading_bot.py)
3. **Emergency stop available** in both modes (command: `emergency`)
4. **Circuit breaker active** in both modes
5. **Same risk limits** apply to both modes

---

## 12. TESTING RECOMMENDATIONS

### For Paper Trading
- Test strategy logic without financial risk
- Validate exit conditions
- Verify database persistence
- Test command interface

### Before Going Live
1. Run paper trading for several days
2. Verify all risk limits are set correctly
3. Check that circuit breaker logic works
4. Ensure emergency stop is operational
5. Validate all database records

### Live Trading Checklist
- [ ] Verify API credentials are correct
- [ ] Confirm capital/leverage settings
- [ ] Review all risk parameters
- [ ] Check trading hours (9:15 AM - 3:30 PM IST)
- [ ] Test with small positions first
- [ ] Monitor first few trades carefully
- [ ] Keep emergency command ready

