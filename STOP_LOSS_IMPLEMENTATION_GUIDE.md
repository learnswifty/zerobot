# Stop Loss Implementation Guide for Live Trading

## 🎯 Quick Summary

**Problem**: Current code does NOT place stop-loss orders on Zerodha exchange. It only monitors in software.

**Risk**: If program crashes or network fails, you have ZERO stop loss protection in live trading.

**Solution**: Implement exchange-level SL-M (Stop Loss Market) orders.

---

## 🚀 Recommended Approach: HYBRID METHOD

**Strategy**:
- Place SL-M order on exchange at entry (safety net)
- Update SL in software for precise trailing
- Update exchange SL only when it moves significantly (0.5%+)

**Benefits**:
- ✅ Protected even if program crashes
- ✅ Protected even if internet fails
- ✅ Precise trailing in normal conditions
- ✅ Minimal API calls

---

## 📝 Code Changes Required

### 1. Add SL Order Tracking to Trade Class

**File**: `trading_bot.py`
**Location**: After line 93 (in Trade.__init__)

```python
def __init__(self, symbol: str, direction: str, entry_time: datetime,
             entry_price: float, quantity: int, stop_loss: float,
             target_price: float = None, trade_id: int = None):
    # ... existing code ...
    self.order_id_entry = None
    self.order_id_exit = None

    # ADD THESE TWO LINES:
    self.sl_order_id = None  # Track exchange SL order
    self.last_exchange_sl = None  # Last SL level on exchange
```

---

### 2. Modify OrderManager to Support SL-M Orders

**File**: `trading_bot.py`
**Location**: Modify place_order method (line 170)

**Current signature**:
```python
def place_order(self, symbol: str, transaction_type: str, quantity: int,
                order_type: str = 'MARKET', price: float = None,
                trigger_price: float = None) -> Optional[str]:
```

This is already correct! The `trigger_price` parameter exists.

**Just ensure it's being used correctly** (verify line 223):
```python
if trigger_price:
    order_params['trigger_price'] = trigger_price
```

✅ This is already present - no changes needed here.

---

### 3. Add Method to Place SL Order on Exchange

**File**: `trading_bot.py`
**Location**: Add this method after line 757 (after calculate_position_size)

```python
def _place_stop_loss_order(self, symbol: str, trade: Trade) -> Optional[str]:
    """
    Place stop-loss order on exchange (live mode only).

    Args:
        symbol: Trading symbol
        trade: Trade object with stop loss level

    Returns:
        order_id if successful, None otherwise
    """
    # Skip in paper mode
    if self.order_manager.paper_mode:
        return None

    transaction_type = 'SELL' if trade.direction == 'LONG' else 'BUY'

    try:
        order_id = self.order_manager.place_order(
            symbol=symbol,
            transaction_type=transaction_type,
            quantity=trade.quantity,
            order_type='SL-M',  # Stop Loss Market
            trigger_price=trade.stop_loss
        )

        if order_id:
            self.logger.info(
                f"[SL ORDER] Placed {order_id} for {symbol} | "
                f"Trigger: ₹{trade.stop_loss:.2f} | Qty: {trade.quantity}"
            )
        else:
            self.logger.error(f"[SL ORDER] Failed to place SL order for {symbol}")

        return order_id

    except Exception as e:
        self.logger.error(f"[SL ORDER] Exception placing SL order for {symbol}: {str(e)}")
        return None
```

---

### 4. Place SL Order After Entry

**File**: `trading_bot.py`
**Location**: Modify enter_trade method at line ~870 (after entry order completes)

Find this section (around line 854-871):
```python
# Wait for order completion
if not self.order_manager.wait_for_order_completion(order_id):
    self.logger.error(f"Entry order for {symbol} did not complete")
    # Restore buying power
    self.buying_power += position_value
    return None

# Create trade object
trade = Trade(symbol, direction, entry_time, entry_price, quantity,
              stop_loss, target_price)
trade.order_id_entry = order_id
trade.trade_id = trade_id

# Save to database
self.db.insert_trade(trade)

# Add to active trades
self.active_trades[symbol] = trade
```

**ADD AFTER line 871**:
```python
# Add to active trades
self.active_trades[symbol] = trade

# ADD THIS BLOCK:
# Place stop-loss order on exchange (live mode only)
if not self.order_manager.paper_mode and TradingConfig.USE_EXCHANGE_STOP_LOSS:
    sl_order_id = self._place_stop_loss_order(symbol, trade)
    if sl_order_id:
        trade.sl_order_id = sl_order_id
        trade.last_exchange_sl = trade.stop_loss
        self.logger.info(f"[SL ORDER] Protection active for {symbol}")
    else:
        self.logger.warning(
            f"[SL ORDER] No exchange SL placed for {symbol} - "
            f"software monitoring only (RISKY!)"
        )
```

---

### 5. Update Exchange SL When Trailing

**File**: `trading_bot.py`
**Location**: Modify monitor_active_trades at line ~1086

Find this section:
```python
# Update trailing stop
if self.exit_strategy.use_trailing_sl:
    old_sl = trade.stop_loss
    trade.update_trailing_stop(ltp, self.exit_strategy.trailing_sl_percent)

    # Only update database if stop loss actually changed
    if trade.stop_loss != old_sl:
        self.db.update_trade(trade.trade_id, {'stop_loss': trade.stop_loss})
        self.logger.info(f"{symbol} trailing SL updated: ₹{old_sl:.2f} -> ₹{trade.stop_loss:.2f}")
```

**REPLACE WITH**:
```python
# Update trailing stop
if self.exit_strategy.use_trailing_sl:
    old_sl = trade.stop_loss
    trade.update_trailing_stop(ltp, self.exit_strategy.trailing_sl_percent)

    # Only update database if stop loss actually changed
    if trade.stop_loss != old_sl:
        self.db.update_trade(trade.trade_id, {'stop_loss': trade.stop_loss})
        self.logger.info(f"{symbol} trailing SL updated: ₹{old_sl:.2f} -> ₹{trade.stop_loss:.2f}")

        # UPDATE EXCHANGE SL IF MOVED SIGNIFICANTLY (live mode only)
        if (not self.order_manager.paper_mode and
            TradingConfig.USE_EXCHANGE_STOP_LOSS and
            trade.last_exchange_sl is not None):

            # Calculate how much SL moved as percentage
            sl_move_percent = abs(
                (trade.stop_loss - trade.last_exchange_sl) / trade.last_exchange_sl
            ) * 100

            # Update exchange SL if moved by threshold or more
            if sl_move_percent >= TradingConfig.SL_UPDATE_THRESHOLD_PERCENT:
                self._update_exchange_sl_order(trade)
```

---

### 6. Add Method to Update Exchange SL Order

**File**: `trading_bot.py`
**Location**: Add after _place_stop_loss_order method

```python
def _update_exchange_sl_order(self, trade: Trade) -> bool:
    """
    Update stop-loss order on exchange by canceling old and placing new.

    Args:
        trade: Trade object with updated stop loss

    Returns:
        True if successful, False otherwise
    """
    if self.order_manager.paper_mode:
        return True

    try:
        # Cancel existing SL order
        if trade.sl_order_id:
            cancel_success = self.order_manager.cancel_order(trade.sl_order_id)
            if not cancel_success:
                self.logger.warning(
                    f"[SL ORDER] Failed to cancel old SL order {trade.sl_order_id} "
                    f"for {trade.symbol}"
                )

        # Place new SL order at updated level
        new_sl_order_id = self._place_stop_loss_order(trade.symbol, trade)

        if new_sl_order_id:
            trade.sl_order_id = new_sl_order_id
            trade.last_exchange_sl = trade.stop_loss
            self.logger.info(
                f"[SL ORDER] Updated for {trade.symbol}: "
                f"₹{trade.last_exchange_sl:.2f} (order: {new_sl_order_id})"
            )
            return True
        else:
            self.logger.error(
                f"[SL ORDER] Failed to place updated SL order for {trade.symbol}"
            )
            return False

    except Exception as e:
        self.logger.error(
            f"[SL ORDER] Exception updating SL order for {trade.symbol}: {str(e)}"
        )
        return False
```

---

### 7. Cancel SL Order on Exit

**File**: `trading_bot.py`
**Location**: Modify exit_trade method at line ~925

Find the beginning of exit_trade:
```python
def exit_trade(self, trade: Trade, exit_price: float, reason: str) -> bool:
    """Exit a trade and return success status"""

    # Place exit order
    transaction_type = 'SELL' if trade.direction == 'LONG' else 'BUY'
    order_id = self.order_manager.place_order(trade.symbol, transaction_type, trade.quantity, price=exit_price)
```

**INSERT BEFORE "Place exit order"**:
```python
def exit_trade(self, trade: Trade, exit_price: float, reason: str) -> bool:
    """Exit a trade and return success status"""

    # ADD THIS BLOCK:
    # Cancel SL order first (if exists in live mode)
    if not self.order_manager.paper_mode and trade.sl_order_id:
        self.logger.info(f"[SL ORDER] Canceling SL order {trade.sl_order_id} for {trade.symbol}")
        cancel_success = self.order_manager.cancel_order(trade.sl_order_id)
        if cancel_success:
            trade.sl_order_id = None
        else:
            self.logger.warning(
                f"[SL ORDER] Failed to cancel SL order {trade.sl_order_id}. "
                f"Will proceed with exit anyway."
            )

    # Place exit order
    transaction_type = 'SELL' if trade.direction == 'LONG' else 'BUY'
    order_id = self.order_manager.place_order(trade.symbol, transaction_type, trade.quantity, price=exit_price)
```

---

### 8. Add Configuration Settings

**File**: `config.py`
**Location**: Add after line 112 (after ENABLE_TRAILING_STOP)

```python
# Stop Loss Management (for live trading)
USE_EXCHANGE_STOP_LOSS = True  # Place SL orders on exchange (HIGHLY RECOMMENDED for live trading)
SL_ORDER_TYPE = 'SL-M'  # SL-M (Stop Loss Market) - guaranteed execution
SL_UPDATE_THRESHOLD_PERCENT = 0.5  # Update exchange SL when trailing moves this % or more
```

**Explanation**:
- `USE_EXCHANGE_STOP_LOSS = True`: Enables exchange SL orders (MUST be True for live trading)
- `SL_ORDER_TYPE = 'SL-M'`: Use market orders when SL triggers (guaranteed execution)
- `SL_UPDATE_THRESHOLD_PERCENT = 0.5`: Only update exchange SL when it moves 0.5% or more (reduces API calls)

---

### 9. Update Database Schema (Optional but Recommended)

**File**: `database.py`
**Location**: Modify trades table schema (around line 100)

Add these columns to track SL orders:
```sql
CREATE TABLE IF NOT EXISTS trades (
    -- ... existing columns ...
    order_id_entry TEXT,
    order_id_exit TEXT,

    -- ADD THESE LINES:
    sl_order_id TEXT,  -- Current active SL order ID
    last_exchange_sl REAL,  -- Last SL level on exchange

    notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
```

To apply this change, you'll need to either:
- Migrate existing database (add columns)
- Or start with fresh database

---

## 🧪 Testing Procedure

### Phase 1: Paper Trading Testing

1. **Set config**:
```python
ENABLE_PAPER_TRADING = True
USE_EXCHANGE_STOP_LOSS = False  # Should be False in paper mode
```

2. **Test**:
- [ ] Entry orders work as before
- [ ] Trailing SL updates work
- [ ] No errors about SL orders
- [ ] Exits work normally

### Phase 2: Live Testing with Small Capital

1. **Set config**:
```python
ENABLE_PAPER_TRADING = False
USE_EXCHANGE_STOP_LOSS = True  # Enable exchange SL
DEFAULT_CAPITAL = 5000  # Start small!
MAX_OPEN_POSITIONS = 1  # Only 1 position initially
```

2. **First Trade Test**:
- [ ] Enter trade manually or via bot
- [ ] **Check Zerodha dashboard** - you should see TWO orders:
  - ✅ Entry order (COMPLETE)
  - ✅ SL-M order (PENDING/TRIGGER PENDING)
- [ ] Verify SL order trigger price matches your stop loss
- [ ] Monitor trailing SL updates in logs
- [ ] When SL updates on exchange, check Zerodha dashboard
  - Old SL order should be CANCELLED
  - New SL order should be PENDING
- [ ] Exit normally (target or manual) and verify SL order is cancelled

3. **Test SL Execution** (optional but recommended):
- [ ] Enter a trade
- [ ] Verify SL-M order on exchange
- [ ] Let price hit stop loss
- [ ] Verify SL-M order executes
- [ ] Check slippage (difference between trigger and execution price)

### Phase 3: Network Failure Test

1. **Setup**:
- [ ] Enter a trade in live mode
- [ ] Verify SL-M order on exchange
- [ ] Note the SL trigger price

2. **Test**:
- [ ] Stop the Python program (Ctrl+C)
- [ ] Verify in Zerodha dashboard that SL order is still active
- [ ] (Optionally) Let price approach SL to verify it still triggers

3. **Result**:
- ✅ SL order should remain active on exchange
- ✅ This proves you're protected even if program stops

---

## 📊 What You'll See in Logs

### Successful Entry with Exchange SL

```
[INFO] Order placed: 241102000123456 | TCS | BUY 10 @ ₹3500.00
[INFO] ✅ LONG entry: TCS | Qty: 10 | Entry: ₹3500.00 | SL: ₹3450.00 | Target: ₹3600.00
[INFO] [SL ORDER] Placed 241102000123457 for TCS | Trigger: ₹3450.00 | Qty: 10
[INFO] [SL ORDER] Protection active for TCS
```

### Trailing SL Update (Software Only)

```
[INFO] TCS trailing SL updated: ₹3450.00 -> ₹3485.00
```

### Exchange SL Update (When Threshold Met)

```
[INFO] TCS trailing SL updated: ₹3485.00 -> ₹3540.00
[INFO] Order 241102000123457 cancelled
[INFO] [SL ORDER] Placed 241102000123458 for TCS | Trigger: ₹3540.00 | Qty: 10
[INFO] [SL ORDER] Updated for TCS: ₹3540.00 (order: 241102000123458)
```

### Exit with SL Cancellation

```
[INFO] [SL ORDER] Canceling SL order 241102000123458 for TCS
[INFO] Order 241102000123458 cancelled
[INFO] Order placed: 241102000123459 | TCS | SELL 10 @ ₹3600.00
[INFO] ✅ LONG exit: TCS | Entry: ₹3500.00 | Exit: ₹3600.00 | P&L: ₹850.00 | Reason: TARGET
```

---

## ⚠️ Important Warnings

### 1. Order Type: SL-M vs SL

**SL-M (Stop Loss Market)** - RECOMMENDED:
- ✅ Guaranteed execution when SL hit
- ❌ No price protection (market order)
- ✅ Best for most situations

**SL (Stop Loss Limit)**:
- ✅ Price protection (limit order)
- ❌ May not execute if price moves fast
- ⚠️ Risk of not exiting at all

**Recommendation**: Use SL-M for safety

### 2. Slippage on SL-M Orders

Example:
- SL trigger: ₹3450
- Actual execution: ₹3445 (5 points slippage)
- This is normal for market orders
- Consider this in your risk calculations

### 3. Brief Window During SL Update

When updating exchange SL:
1. Old SL order cancelled (brief moment)
2. New SL order placed
3. Small window (~1-2 seconds) with no exchange protection
4. Software monitoring still active as backup

**Mitigation**: Only update when price moves favorably (already moving away from SL)

### 4. API Rate Limits

Zerodha allows:
- 10 requests/second
- 3000 requests/day

With exchange SL updates:
- More API calls than pure monitoring
- Still well within limits for normal trading
- Circuit breaker protects against excessive calls

### 5. Paper Trading Mode

In paper mode:
- `USE_EXCHANGE_STOP_LOSS` should be False
- No real orders placed
- Software monitoring only (this is fine for testing)

---

## 🎯 Quick Decision Checklist

**Before going live, ensure**:

- [ ] Code changes implemented from this guide
- [ ] `USE_EXCHANGE_STOP_LOSS = True` in config.py
- [ ] Tested thoroughly in paper mode
- [ ] Tested with small capital in live mode
- [ ] Verified SL orders visible in Zerodha dashboard
- [ ] Tested SL order cancellation on exit
- [ ] Tested trailing SL updates
- [ ] Understand slippage on SL-M orders
- [ ] Emergency command ready: `emergency`
- [ ] Stable internet connection verified

**If any checkbox is unchecked** → DO NOT go live with real capital!

---

## 🔗 Related Files

- `LIVE_TRADING_RISK_ANALYSIS.md` - Detailed risk analysis
- `PAPER_VS_LIVE_TRADING.md` - Complete comparison
- `QUICK_REFERENCE.md` - Quick lookup guide

---

## 🆘 Getting Help

If something doesn't work:

1. Check logs in `logs/trading_bot.log`
2. Check Zerodha dashboard for order status
3. Review this guide step-by-step
4. Test with paper trading first
5. Use small capital for live testing

---

**Remember**: Your money, your responsibility. Test thoroughly before going live!

---

*Last Updated: 2024-11-02*
