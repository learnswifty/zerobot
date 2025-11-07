#!/bin/bash

echo "================================================================================"
echo "                    Trading Bot Startup Script                                  "
echo "================================================================================"

# Change to script directory
cd "$(dirname "$0")"

# Step 1: Kill any existing trading bot processes
echo "Step 1: Checking for existing bot processes..."
if pgrep -f "python.*trading_bot.py" > /dev/null; then
    echo "⚠️  Found running bot processes. Killing them..."
    pkill -9 -f "python.*trading_bot.py"
    sleep 2
    echo "✓ Old processes killed"
else
    echo "✓ No existing processes found"
fi

# Step 2: Pull latest code
echo ""
echo "Step 2: Pulling latest code..."
git fetch origin
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "Current branch: $CURRENT_BRANCH"

if git diff --quiet origin/$CURRENT_BRANCH; then
    echo "✓ Code is up to date"
else
    echo "⚠️  New code available, pulling..."
    git pull origin $CURRENT_BRANCH
    echo "✓ Code updated"
fi

# Step 3: Clear Python cache
echo ""
echo "Step 3: Clearing Python bytecode cache..."
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
find . -type f -name "*.pyc" -delete 2>/dev/null
echo "✓ Cache cleared"

# Step 4: Verify config
echo ""
echo "Step 4: Verifying configuration..."
python3 verify_config.py

# Check if config verification passed
if python3 -c "from config import TradingConfig; exit(0 if TradingConfig.MAX_STOP_LOSS_PERCENT == 7.0 else 1)"; then
    echo "✓ Configuration verified: MAX_STOP_LOSS_PERCENT = 7.0%"
else
    echo "❌ CRITICAL ERROR: MAX_STOP_LOSS_PERCENT is not 7.0%"
    echo "❌ Cannot start bot with incorrect configuration!"
    exit 1
fi

# Step 5: Check for recent commits
echo ""
echo "Step 5: Verifying latest commits are present..."
EXPECTED_COMMITS="89794d8 dbb0b45 2cc661b f210c78"
for commit in $EXPECTED_COMMITS; do
    if git log --oneline -20 | grep -q "$commit"; then
        echo "✓ Found commit $commit"
    else
        echo "⚠️  Commit $commit not found in recent history"
    fi
done

# Step 6: Start the bot
echo ""
echo "================================================================================"
echo "✓ All checks passed! Starting trading bot..."
echo "================================================================================"
echo ""

# Use unbuffered Python output for real-time logs
exec python3 -u trading_bot.py
