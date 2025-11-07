#!/usr/bin/env python3
"""
Config Verification Script
Run this to verify the MAX_STOP_LOSS_PERCENT value loaded by Python
"""

import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 80)
print("CONFIG VERIFICATION")
print("=" * 80)

# Check file directly
print("\n1. Checking config.py file directly:")
with open('config.py', 'r') as f:
    for line in f:
        if 'MAX_STOP_LOSS_PERCENT' in line and '=' in line and not line.strip().startswith('#'):
            print(f"   {line.strip()}")

# Import and check
print("\n2. Importing config module:")
try:
    from config import TradingConfig
    print(f"   TradingConfig.MAX_STOP_LOSS_PERCENT = {TradingConfig.MAX_STOP_LOSS_PERCENT}")
    print(f"   TradingConfig.MIN_STOP_LOSS_PERCENT = {TradingConfig.MIN_STOP_LOSS_PERCENT}")
except Exception as e:
    print(f"   ERROR: {e}")

# Check __pycache__
print("\n3. Checking bytecode cache:")
cache_path = "__pycache__/config.cpython-311.pyc"
if os.path.exists(cache_path):
    import time
    mtime = os.path.getmtime(cache_path)
    mtime_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime))
    print(f"   Cache exists: {cache_path}")
    print(f"   Last modified: {mtime_str}")
else:
    print("   No cache found")

# Check source file
print("\n4. Checking source file:")
source_path = "config.py"
if os.path.exists(source_path):
    import time
    mtime = os.path.getmtime(source_path)
    mtime_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(mtime))
    print(f"   Source exists: {source_path}")
    print(f"   Last modified: {mtime_str}")

print("\n" + "=" * 80)
print("EXPECTED: MAX_STOP_LOSS_PERCENT = 7.0")
print("=" * 80)
