# 🚀 How to Start the Trading Bot

## ✅ RECOMMENDED METHOD (Automatic Cleanup)

Simply run the startup script - it handles everything automatically:

```bash
cd /home/user/zerobot
./start_bot.sh
```

The startup script automatically:
- ✅ Kills old bot processes
- ✅ Pulls latest code from git
- ✅ Clears Python bytecode cache
- ✅ Verifies configuration (MAX_STOP_LOSS = 7.0%)
- ✅ Checks all critical commits are present
- ✅ Starts the bot with correct config

---

## ⚠️ OLD METHOD (Manual - NOT RECOMMENDED)

If you run `python3 trading_bot.py` directly, you risk:
- ❌ Running with stale Python cache (2.0% bug)
- ❌ Running old code version
- ❌ Multiple bot instances running

**The bot will now REFUSE to start** if it detects incorrect config!

---

## 🔧 If Bot Refuses to Start

If you see this error:
```
❌ CRITICAL ERROR: Invalid Configuration Detected!
❌ MAX_STOP_LOSS_PERCENT = 2.0% (expected 7.0%)
```

**Solution:** Just run the startup script:
```bash
./start_bot.sh
```

---

## 📋 What Changed Recently

### Commit 89794d8: Fix ABB API Rate Limit Spam
- Auto-stops stocks after 3 failed instrument token lookups
- Prevents 80+ error messages spamming the log

### Commit dbb0b45: Config Verification at Startup
- Displays MAX_STOP_LOSS_PERCENT at startup
- Bot refuses to run with incorrect config
- Prevents "2.0% bug" from stale Python cache

### Commit 2cc661b: Prevent Auto Re-Entry After Manual Exit
- When you manually exit a position, bot auto-stops that stock
- Prevents unwanted immediate re-entry
- Use `resume <SYMBOL>` to re-enable monitoring

### Commit f210c78: Enhanced Logging
- Entry logs show: SL%, position size, RR ratio
- Exit logs show: P&L%, trade duration
- Fixed "max entries" log spam

---

## 📊 Verify Bot is Running Latest Code

After startup, check the logs show:

```
✓ Authenticated as: Keyurbhai Ukabhai Navadiya (IYF261)
⚡ Rate limiter initialized: 10/sec, 200/min
🚨 Emergency stop enabled - Use 'emergency' command to activate
================================================================================
🚀 TRADING BOT STARTED
Capital: ₹10,000 | Leverage: 5.0x | Buying Power: ₹50,000
================================================================================
[PAPER] Paper trading mode is ENABLED. No live orders will be placed.

⚙️  CONFIG: MAX_STOP_LOSS = 7.0% | MIN_STOP_LOSS = 0.5%     ← Must be 7.0%!
⚙️  CONFIG: MAX_ENTRIES_PER_STOCK = 2 | MAX_OPEN_POSITIONS = 5
⚙️  Stop Loss Limits: 0.5% - 7.0%
```

If you see **7.0%** → ✅ Correct!
If you see **2.0%** → ❌ Bot will refuse to start!

---

## 🆘 Troubleshooting

### Problem: "Permission denied" when running ./start_bot.sh
```bash
chmod +x start_bot.sh
./start_bot.sh
```

### Problem: Bot still shows 2.0% despite everything
```bash
# Nuclear option - completely clean restart:
pkill -9 -f trading_bot.py
rm -rf __pycache__
find . -name "*.pyc" -delete
python3 verify_config.py  # Must show 7.0%
./start_bot.sh
```

### Problem: "Too many requests" errors for a stock
This is now automatically handled:
- Stock will auto-stop after 3 failed API calls
- Prevents log spam and API quota waste
- Check symbol name is correct (e.g., "ABB" not "ABB.NSE")

---

## 📞 Support

If issues persist:
1. Run `python3 verify_config.py` - paste output
2. Run `git log --oneline -5` - paste output
3. Share startup logs (first 20 lines after bot starts)
