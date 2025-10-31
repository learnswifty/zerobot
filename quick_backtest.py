#!/usr/bin/env python3
"""
Quick Start Example - Run Backtest with Default Settings
=========================================================
This script runs a backtest with sensible defaults for quick testing.
"""

import os
from datetime import datetime, timedelta
from intraday_strategy_backtest import IntradayStrategyBacktester
from dotenv import load_dotenv

# Colors for output
class Colors:
    HEADER = '\033[95m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'


def quick_backtest():
    """Run a quick backtest with default settings"""

    # Load environment
    load_dotenv()
    api_key = os.getenv('ZERODHA_API_KEY')
    access_token = os.getenv('ZERODHA_ACCESS_TOKEN')

    if not api_key or not access_token:
        print(f"{Colors.FAIL}❌ API credentials not found!{Colors.ENDC}")
        print(f"{Colors.WARNING}Please run: python auth_helper.py{Colors.ENDC}")
        return

    # Initialize backtester
    print(f"\n{Colors.HEADER}{Colors.BOLD}🚀 Quick Backtest - Last 5 Trading Days{Colors.ENDC}\n")

    backtester = IntradayStrategyBacktester(api_key, access_token)
    print(f"{Colors.OKGREEN}✓ Connected to Zerodha{Colors.ENDC}\n")

    # Default settings
    print(f"{Colors.BOLD}Configuration:{Colors.ENDC}")
    print(f"  📅 Date Range: Last 5 trading days")
    print(f"  📉 Direction: SHORT (bearish)")
    print(f"  📊 Stocks: Top 5 liquid F&O stocks")
    print(f"  💰 Margin: ₹10,000 per trade")
    print(f"  ⚡ Leverage: 5x")
    print(f"  💵 Position Size: ₹50,000\n")

    # Date range - last 5 trading days (approximately last week)
    to_date = datetime.now()
    from_date = to_date - timedelta(days=10)  # Go back 10 days to get 5 trading days

    # Top liquid stocks
    stocks = ['MMCT', 'SAIL', 'ADANIGREEN']

    # Direction - SHORT for example
    direction = 'SHORT'

    print(f"{Colors.BOLD}Starting backtest...{Colors.ENDC}\n")

    # Run backtest
    all_trades = []
    for stock in stocks:
        try:
            trades = backtester.backtest_stock(stock, from_date, to_date, direction)
            all_trades.extend(trades)
        except Exception as e:
            print(f"{Colors.FAIL}Error with {stock}: {e}{Colors.ENDC}")

    # Display results
    if all_trades:
        backtester.display_results(all_trades)
        print(f"\n{Colors.OKGREEN}✓ Backtest complete!{Colors.ENDC}\n")
    else:
        print(f"{Colors.WARNING}⚠ No trades generated{Colors.ENDC}")
        print("This could mean:")
        print("  - No trading days in the selected range")
        print("  - No setups matched the criteria")
        print("  - Data not available for these stocks")


if __name__ == "__main__":
    try:
        quick_backtest()
    except KeyboardInterrupt:
        print(f"\n{Colors.WARNING}⚠ Cancelled by user{Colors.ENDC}")
    except Exception as e:
        print(f"{Colors.FAIL}❌ Error: {e}{Colors.ENDC}")
        import traceback
        traceback.print_exc()