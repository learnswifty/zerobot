#!/usr/bin/env python3
"""
Quick credential setup for backtest scripts
This creates a .env file with your Zerodha credentials
"""

import os

print("=" * 60)
print("  Zerodha Credentials Setup")
print("=" * 60)

# Check if .env already exists
if os.path.exists('.env'):
    print("\n✓ .env file already exists")
    with open('.env', 'r') as f:
        content = f.read()
        has_api_key = 'ZERODHA_API_KEY' in content
        has_token = 'ZERODHA_ACCESS_TOKEN' in content

        if has_api_key and has_token:
            print("✓ API Key found")
            print("✓ Access Token found")
            print("\n✓ Credentials are set up correctly!")
        else:
            print("⚠️  .env file exists but missing credentials")
            if not has_api_key:
                print("   Missing: ZERODHA_API_KEY")
            if not has_token:
                print("   Missing: ZERODHA_ACCESS_TOKEN")
else:
    print("\n⚠️  .env file not found - creating new one")

    print("\nPlease enter your Zerodha credentials:")
    print("(You can find these in your Kite Connect app settings)")

    api_key = input("\nAPI Key: ").strip()
    access_token = input("Access Token: ").strip()

    if not api_key or not access_token:
        print("\n❌ Both API Key and Access Token are required!")
        exit(1)

    # Create .env file
    with open('.env', 'w') as f:
        f.write(f"ZERODHA_API_KEY={api_key}\n")
        f.write(f"ZERODHA_ACCESS_TOKEN={access_token}\n")

    print("\n✓ .env file created successfully!")
    print("✓ Credentials saved")

print("\n" + "=" * 60)
print("You can now run the backtest:")
print("  python3 backtest_first_candle_retest.py")
print("=" * 60)
