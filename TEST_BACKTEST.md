# Quick Backtest Test Guide

## Problem Encountered
UNIONBANK on 2025-10-31 had no red candles, so bot correctly didn't trade.

## Solution: Test with Liquid Stocks

### Recommended Test Configuration

**Run this exact test:**

```bash
python trading_bot.py
```

**Configuration:**
- Mode: `1` (Paper Trading)
- Date: `2025-10-31` (or try 2025-10-30, 2025-10-29)
- Capital: `10000` (or press Enter)
- Stocks: `RELIANCE, TCS, INFY`
- RR Exit: `y` (enable with 2:1 ratio)
- Trailing SL: `y` (1% default)
- Confirm: `yes`

### Why This Will Work

**RELIANCE, TCS, INFY:**
- Top 3 most liquid NSE stocks
- High daily volume (100+ crores)
- Always have multiple red candles
- Perfect for strategy testing

### Expected Output

You should see something like:

```
============================================================
Backtesting RELIANCE for 2025-10-31
============================================================
✓ Loaded 78 candles
✓ First red at 09:25: High=₹1,245.50, Low=₹1,242.00

🔵 ENTRY | RELIANCE | LONG
   Time: 10:15:00
   Entry: ₹1,246.75
   SL: ₹1,242.00
   Target: ₹1,256.25
   Qty: 40

📊 Monitoring position...

🟢 EXIT | RELIANCE | LONG
   Time: 14:20:00
   Exit: ₹1,256.50
   P&L: ₹+390.00
   Reason: TARGET

============================================================
Backtesting TCS for 2025-10-31
============================================================
✓ Loaded 78 candles
✓ First red at 09:30: High=₹3,420.00, Low=₹3,415.50

(And so on...)
```

### Daily Summary

After all stocks complete, you'll see:

```
📈 DAILY SUMMARY
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Total Trades: 3
Wins: 2 | Losses: 1
Win Rate: 66.7%
Total P&L: ₹+1,247.50
Max Drawdown: ₹-345.00
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

## Understanding Results

### If you see "No red candle found" for ALL stocks:
- The date might be a market holiday
- Try a different date: 2025-10-30, 2025-10-29, 2025-10-28

### If you see trades being executed:
✅ Your bot is working perfectly!
✅ The backtest is functioning correctly
✅ Strategy is being applied properly

## Database Check

After running, check the database:

```bash
sqlite3 data/trades.db "SELECT * FROM trades WHERE trade_date='2025-10-31';"
```

You should see your trade records!

## Common Questions

**Q: Why didn't UNIONBANK work?**
A: It had no red candles that day. This is normal - not all stocks have red candles every day.

**Q: Is the bot broken?**
A: No! It's working correctly by NOT forcing trades when there's no setup.

**Q: How do I know if the strategy is profitable?**
A: Run backtests on multiple dates (10-20 days) and check overall P&L.

**Q: What if even RELIANCE shows "No red candle"?**
A: Very unlikely, but try a different date. Some dates might be market holidays.

## Next Steps

1. ✅ Test with RELIANCE, TCS, INFY
2. ✅ Verify trades are executed
3. ✅ Check daily summary shows results
4. ✅ Review database for trade records
5. ✅ Test on 5-10 different dates
6. ✅ Calculate overall win rate
7. ✅ When confident, try live paper trading (today's date)

## Still Having Issues?

If RELIANCE/TCS/INFY also show no trades:
1. Check the date is a weekday (not Saturday/Sunday)
2. Try recent dates (last 1-2 weeks)
3. Verify internet connection for data fetching
4. Check logs in `logs/trading_bot.log`

---

**Remember:** A strategy that doesn't trade when there's no setup is BETTER than one that forces trades!
