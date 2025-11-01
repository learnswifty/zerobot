# 🎮 Interactive Trading Mode Guide

## New Feature: Interactive Startup Flow

The ZeroBot now has a **user-friendly interactive startup** that asks for your preferences!

---

## 🚀 Quick Start

```bash
python trading_bot.py
```

You'll be guided through 5 simple steps:

---

## 📋 Step-by-Step Walkthrough

### **Step 1: Trading Mode Selection**

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                         Trading Mode Selection                               ║
╚══════════════════════════════════════════════════════════════════════════════╝

Choose trading mode:

  1. Paper Trading - Simulated orders (SAFE, recommended for testing)
  2. Live Trading  - Real orders with real money (RISK)

Enter choice (1/2) [default: 1]: _
```

**Options:**
- **Press Enter** → Paper Trading (default, safe)
- **Type 1** → Paper Trading
- **Type 2** → Live Trading (requires additional confirmation)

---

### **Step 2A: Date Selection (Paper Trading Only)**

If you selected **Paper Trading**, you'll see:

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                   Date Selection (Paper Trading)                             ║
╚══════════════════════════════════════════════════════════════════════════════╝

Choose date for paper trading backtest:

  • Press ENTER for today's date (live paper trading)
  • Enter date in YYYY-MM-DD format (historical backtest)

Note: Historical dates will fetch past data for backtesting

Enter date or press ENTER for today: _
```

**Options:**
- **Press Enter** → Today's date (live paper trading)
- **Type 2025-01-15** → Historical backtest for that date

**Validation:**
- ✅ Cannot select future dates
- ⚠️  Warns if date is >30 days old (data may be limited)

---

### **Step 2B: Live Trading (No Date Prompt)**

If you selected **Live Trading**, you must type "CONFIRM":

```
⚠️  WARNING: LIVE TRADING SELECTED!
Real money will be used. Real profits and losses will occur.

Type 'CONFIRM' to proceed with live trading: _
```

After confirmation:
- Uses **today's date automatically** (no date prompt)
- Proceeds to capital configuration

---

### **Step 3: Capital Configuration**

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                         Capital Configuration                                ║
╚══════════════════════════════════════════════════════════════════════════════╝

Default capital: ₹10,000
Press Enter to use default, or enter custom amount

Enter capital amount (or press Enter for ₹10,000): _
```

**Options:**
- **Press Enter** → ₹10,000 (default)
- **Type amount** → Custom capital (e.g., 25000)

---

### **Step 4: Stock Selection**

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                            Stock Selection                                   ║
╚══════════════════════════════════════════════════════════════════════════════╝

Enter stock symbols (comma-separated)
Example: RELIANCE, TCS, INFY, HDFCBANK
Note: Use NSE trading symbols

Enter stock symbols: _
```

**Example Input:**
```
RELIANCE, TCS, INFY
```

---

### **Step 5: Exit Strategy Configuration**

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                    Exit Strategy Configuration                               ║
╚══════════════════════════════════════════════════════════════════════════════╝

Configure exit strategies:

1. Enable Risk-Reward exit? (Y/n): _
```

Follow the prompts to configure:
1. Risk-Reward ratio (default: 2.0)
2. Trailing Stop Loss (default: enabled, 1%)

---

### **Step 6: Final Confirmation**

```
╔══════════════════════════════════════════════════════════════════════════════╗
║                        Configuration Summary                                 ║
╚══════════════════════════════════════════════════════════════════════════════╝

Trading Mode: Paper Trading
Trading Date: 2025-11-01
Capital: ₹10,000
Leverage: 5x
Buying Power: ₹50,000
Stocks: RELIANCE, TCS, INFY
Exit Strategy: RR 2.0:1 | Trail 1.0%

Start trading bot? (yes/no): _
```

Type **yes** to start!

---

## 🎯 Common Use Cases

### 1. **Quick Paper Test (Today)**
```
Mode: 1 (or press Enter)
Date: (press Enter for today)
Capital: (press Enter for ₹10,000)
Stocks: RELIANCE, TCS
Strategy: (press Enter for defaults)
Confirm: yes
```
**Result**: Paper trades with today's live data

---

### 2. **Historical Backtest**
```
Mode: 1 (Paper)
Date: 2025-10-25
Capital: 10000
Stocks: INFY, HDFCBANK
Strategy: RR 2:1, Trail 1%
Confirm: yes
```
**Result**: Tests strategy on October 25 data

---

### 3. **Live Trading (Real Money)**
```
Mode: 2 (Live)
Confirm: CONFIRM
Capital: 5000 (start small!)
Stocks: RELIANCE
Strategy: RR 2:1, Trail 1%
Confirm: yes
```
**Result**: Real trades with real money!

---

## 🔐 Safety Features

### **Paper Trading (Default)**
- ✅ Simulated orders only
- ✅ No real money risk
- ✅ Perfect for testing
- ✅ Can use historical dates

### **Live Trading Protection**
- ⚠️  Must type "CONFIRM" (not just 'yes')
- ⚠️  Clear red warnings
- ⚠️  Always uses today (prevents old data trades)
- ⚠️  Shows in final summary

---

## 📊 Visual Indicators

The bot uses **color coding**:

| Color | Meaning |
|-------|---------|
| 🟢 Green | Safe options (Paper mode, defaults) |
| 🔴 Red | Danger (Live trading) |
| 🟡 Yellow | Warnings (old dates, high capital) |
| 🔵 Blue | Information (current settings) |

---

## ⚙️ How It Works Internally

### Paper Trading Mode
```python
is_paper_trading = True
trade_date = "2025-11-01"  # User choice or today

# Orders are simulated
order_id = "PAPER-1730476800000"
# No real API calls for orders
```

### Live Trading Mode
```python
is_paper_trading = False
trade_date = "2025-11-01"  # Always today

# Real API calls
order_id = kite.place_order(...)
# Actual Zerodha orders placed
```

---

## 🎓 Examples

### Example 1: Paper Trading Today
```
$ python trading_bot.py

Trading Mode Selection
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Choose trading mode:
  1. Paper Trading - Simulated orders (SAFE)
  2. Live Trading - Real orders (RISK)

Enter choice (1/2) [default: 1]: ⏎

✓ Selected: Paper Trading Mode (Safe)

Date Selection (Paper Trading)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Choose date for paper trading backtest:
  • Press ENTER for today's date (live paper trading)
  • Enter date in YYYY-MM-DD format (historical backtest)

Enter date or press ENTER for today: ⏎

✓ Selected: Today (2025-11-01) - Live paper trading mode
```

### Example 2: Live Trading
```
Trading Mode Selection
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Choose trading mode:
  1. Paper Trading
  2. Live Trading

Enter choice (1/2) [default: 1]: 2

⚠️  WARNING: LIVE TRADING SELECTED!
Real money will be used. Real profits and losses will occur.

Type 'CONFIRM' to proceed with live trading: CONFIRM

✗ Selected: Live Trading Mode (Real Money)

ℹ Live trading date: 2025-11-01
```

---

## 🔍 Troubleshooting

### "Cannot select future date"
- You entered a date in the future
- **Fix**: Use today or a past date

### "Historical data may be limited"
- Date is >30 days old
- **Fix**: Use a more recent date or confirm to continue

### "Live trading not confirmed"
- You didn't type "CONFIRM" exactly
- **Fix**: Type CONFIRM in all caps

---

## 💡 Pro Tips

1. **Always start with Paper Trading** until you're confident
2. **Press Enter** for defaults = fastest start
3. **Test historical dates** to see how strategy performed
4. **Start with 1-2 stocks** before scaling up
5. **Use small capital** when going live first time

---

## 📝 Summary

**Before This Feature:**
- Had to edit config.py to change paper/live mode
- No date selection
- Less user-friendly

**After This Feature:**
- ✅ Interactive prompts
- ✅ Clear mode selection
- ✅ Date selection for paper trading
- ✅ Safety confirmations
- ✅ Much better UX!

---

**Now you can test strategies on historical dates OR trade live - all from the startup prompts!** 🚀

---

*Last Updated: 2025-11-01*
*Version: 2.1 - Interactive Mode*
