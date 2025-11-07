# 📊 First Candle Breakout Retest Strategy

## 🎯 Strategy Overview

The **First Candle Breakout Retest** is a momentum continuation pattern that forms during the opening 15-30 minutes (3 five-minute candles) of the trading session.

### Key Concept
- Identifies strong opening momentum
- Confirms strength through a pullback/retest
- Enters on breakout continuation
- Targets early morning volatility with institutional participation

---

## 🧠 The 3-Candle Pattern

### 1️⃣ First Candle (09:15-09:20) - The Breakout Candle

**Requirements:**
- ✅ Strong **GREEN** candle
- ✅ Body size: **0.3% to 2.0%**
- ✅ Closes **near the high** (minimal upper wick)
- ✅ **High volume** (above average)
- ✅ Represents institutional buying (smart money)

**What It Means:**
- Bulls are in control from the open
- Strong buying pressure
- Sets the breakout level (high) and support (low)

**Example:**
```
Open:  ₹100.00
High:  ₹100.50  ← Breakout Level
Low:   ₹99.80   ← Support Level
Close: ₹100.45  (body = 0.45%)
```

---

### 2️⃣ Second Candle (09:20-09:25) - The Retest/Trap

**Requirements:**
- ✅ Usually **RED** or weak green
- ✅ **Touches or slightly breaks below** first candle's low
- ✅ Does NOT close way below (invalidates setup)
- ✅ Moderate to high volume (participation, not panic)

**What It Means:**
- Profit-booking from early buyers
- Shakes out weak hands
- Traps shorts who think rally failed
- **This is the pullback/retest phase**

**Example:**
```
Open:  ₹100.45
High:  ₹100.50
Low:   ₹99.75   ← Retests first candle low (₹99.80)
Close: ₹99.90   ← Red candle, but holds above critical support
```

**Psychology:**
- Shorts enter thinking: "Rally is over!"
- Weak longs exit thinking: "I'll re-enter lower"
- Smart money accumulates at support

---

### 3️⃣ Third Candle (09:25-09:30) - The Confirmation

**Requirements:**
- ✅ **GREEN** candle
- ✅ Breaks **above first candle's high**
- ✅ Preferably closes above first candle high
- ✅ **Increased volume** (follow-through buying)

**What It Means:**
- Bulls regain control
- Shorts get squeezed
- Breakout is confirmed
- **Entry signal triggered**

**Example:**
```
Open:  ₹99.90
High:  ₹100.80  ← Breaks first candle high (₹100.50) ✓
Low:   ₹99.85
Close: ₹100.70  ← Strong close above breakout
```

---

## 📐 Entry Rules

### Entry Trigger:
**When third candle breaks above first candle's high**

```python
Entry Price = First Candle High × 1.001  (slightly above breakout)
Stop Loss   = First Candle Low × 0.999   (slightly below support)
```

### Position Sizing:
```python
Position Size = Buying Power / Entry Price
Max Position  = Capital × Leverage / Entry Price
```

### Risk Management:
- Stop Loss must be between **0.5% to 7.0%**
- If SL too tight (< 0.5%) → Skip trade
- If SL too wide (> 7.0%) → Skip trade

---

## 🚪 Exit Rules

### Exit Strategy Options:

#### 1. Risk-Reward Target (Recommended: 2:1)
```python
Risk   = Entry Price - Stop Loss
Reward = Risk × RR Ratio
Target = Entry Price + Reward

Example:
Entry:  ₹100.50
SL:     ₹99.80  (0.70% risk)
RR:     2:1
Target: ₹101.90 (1.40% reward)
```

#### 2. Trailing Stop Loss (Recommended: 1.0%)
- Locks in profits as price moves favorably
- Trails 1% below highest price reached
- Prevents giving back gains

#### 3. Time-Based Exit
- Force exit at **14:55** (before market close)
- Prevents overnight risk
- Books all positions by EOD

#### 4. Stop Loss Hit
- Exit immediately if price hits SL
- Protects capital
- Moves to next opportunity

---

## 📊 Pattern Recognition Logic

### Validation Checklist:

**First Candle:**
- [x] Green candle (close > open)
- [x] Body 0.3% - 2.0%
- [x] Upper wick < 50% of body
- [x] Volume > 80% of average

**Second Candle:**
- [x] Low touches/breaks first candle low
- [x] Close not too far below (within 0.5%)
- [x] Volume sustained

**Third Candle:**
- [x] High breaks first candle high
- [x] Close near or above first high
- [x] Increased volume (follow-through)

**Overall:**
- [x] Pattern completes within 15 minutes (09:15-09:30)
- [x] Stop loss within acceptable range (0.5%-7.0%)
- [x] Sufficient capital for position size

---

## 🔧 How to Run the Backtest

### Method 1: Direct Execution
```bash
cd /home/user/zerobot
python3 backtest_first_candle_retest.py
```

### Method 2: Make Executable
```bash
chmod +x backtest_first_candle_retest.py
./backtest_first_candle_retest.py
```

---

## 📝 Input Flow

The backtest follows the same input flow as the main trading bot:

### 1. Date Selection
```
📅 Select backtest date:
   Format: YYYY-MM-DD (e.g., 2025-11-07)
Enter date: 2025-11-06
```

### 2. Capital Configuration
```
💰 Enter capital amount:
Capital (default ₹10,000): 50000
```

### 3. Stock Selection
```
📈 Enter stock symbols (comma-separated):
   Example: RELIANCE, TCS, INFY
Symbols: RELIANCE,TCS,INFY,HDFCBANK,ICICIBANK
```

### 4. Exit Strategy
```
⚙️  Exit Strategy Configuration:
Enable Risk-Reward exit? (Y/n): y
Enter RR ratio (default 2.0): 2.5

Enable Trailing Stop Loss? (Y/n): y
Enter trailing % (default 1.0): 1.0
```

### 5. Confirmation
```
Configuration Summary:
================================================================================
Date: 2025-11-06
Capital: ₹50,000
Stocks: RELIANCE, TCS, INFY, HDFCBANK, ICICIBANK
Exit Strategy: RR 2.5:1 | Trail 1.0%
================================================================================

Start backtest? (yes/no): yes
```

---

## 📈 Sample Output

### Pattern Identification:
```
================================================================================
Testing RELIANCE
================================================================================
✓ Loaded 75 candles

✅ Pattern Identified!
   Candle 1 (09:15): Body 0.52% | High: ₹2,450.50 | Low: ₹2,442.00
   Candle 2 (09:20): Retest depth 0.12% | Low: ₹2,441.00
   Candle 3 (09:25): Breakout 0.18% | High: ₹2,454.90

   Entry: ₹2,450.75 | SL: ₹2,441.51 (0.38%)

🔵 ENTRY | RELIANCE | LONG | Qty: 10 | Entry: ₹2,450.75 |
   SL: ₹2,441.51 (0.38%) | Position: ₹24,507
   Target: ₹2,469.23 (RR 2.0:1)
```

### Trade Exit:
```
🟢 EXIT | RELIANCE | LONG | Entry: ₹2,450.75 | Exit: ₹2,469.50 |
   P&L: ₹134.50 (+0.55%) | Duration: 47m | Reason: TARGET
```

### Summary:
```
================================================================================
📊 BACKTEST SUMMARY - First Candle Breakout Retest
================================================================================

💰 Starting Capital: ₹50,000.00
💰 Ending Capital:   ₹51,245.80
💰 Net P&L:          ₹1,245.80 (+2.49%)

📊 Total Trades: 5

================================================================================
```

---

## 🎯 Strategy Parameters (Configurable)

In the code, you can adjust these parameters:

```python
self.MIN_FIRST_CANDLE_BODY = 0.3   # Min body % for first candle
self.MAX_FIRST_CANDLE_BODY = 2.0   # Max body % (avoid gaps)
self.RETEST_TOLERANCE = 0.5        # % below first low for retest
self.MIN_VOLUME_RATIO = 1.2        # First candle vs avg volume
```

---

## ⚠️ Important Notes

### When Pattern FAILS:
- ❌ First candle body < 0.3% → Too weak
- ❌ First candle body > 2.0% → Gap risk
- ❌ Second candle closes way below first low → Setup broken
- ❌ Third candle doesn't break first high → No confirmation
- ❌ Stop loss > 7.0% → Risk too high

### Best Results When:
- ✅ Clear 3-candle pattern
- ✅ Increasing volume on 3rd candle
- ✅ Market trending (avoid sideways days)
- ✅ Strong sector/market momentum
- ✅ Stock has liquidity (easy entry/exit)

### Risk Management:
- Never risk more than 1-2% of capital per trade
- Use proper position sizing
- Respect stop losses
- Don't trade every pattern - be selective

---

## 📚 Comparison with Original Strategy

| Feature | Original (First Red Candle) | New (First Candle Retest) |
|---------|----------------------------|---------------------------|
| **Trigger** | Any first red candle | Specific 3-candle pattern |
| **Direction** | Both LONG & SHORT | **LONG only** (bullish) |
| **Entry** | Breakout from red candle | Breakout after retest |
| **Confirmation** | Immediate breakout | Requires pullback + retest |
| **Psychology** | Simple breakout | Trap + squeeze |
| **Timing** | Throughout day | **First 30 minutes only** |
| **Win Rate** | Moderate | **Higher** (better confirmation) |

---

## 🔄 Next Steps

1. **Run Backtests**: Test on historical data
2. **Optimize Parameters**: Adjust body %, retest tolerance
3. **Paper Trade**: Test with simulated orders
4. **Live Trade**: Start small, scale up

---

## 📞 Support

For issues or questions:
- Check logs for detailed pattern detection
- Review why patterns were rejected
- Adjust parameters if too restrictive

**Happy Trading! 🚀**
