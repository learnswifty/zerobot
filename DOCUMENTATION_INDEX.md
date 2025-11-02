# Zerobot Documentation Index

## Complete Paper Trading vs Live Trading Analysis

This directory contains comprehensive documentation analyzing the paper trading and live trading implementation in the Zerobot trading system.

---

## Quick Navigation

Start with your available time:

### 5-10 Minutes
- Read: `QUICK_REFERENCE.md`
- Get immediate understanding of differences

### 30-45 Minutes
- Read: `PAPER_VS_LIVE_TRADING.md` (Sections 1-3)
- Read: `QUICK_REFERENCE.md`
- Understand core differences

### 1-2 Hours
- Read: `PAPER_VS_LIVE_TRADING.md` (all sections)
- Study: `ARCHITECTURE_SUMMARY.md`
- Review: Key sections of `config.py`
- Comprehensive understanding

### 2-3 Hours
- Read all documentation
- Study `trading_bot.py` (OrderManager class)
- Review `database.py` schema
- Understand full architecture

---

## Documentation Files

### 1. EXPLORATION_SUMMARY.txt (This Month's Analysis)
**Length**: 12 KB  
**Time to read**: 10 minutes  
**Purpose**: Executive summary of findings

Provides:
- Key findings summary
- 9 critical aspects analyzed
- File reference table
- Go-live checklist
- Recommendations

**Start here for overview**

---

### 2. QUICK_REFERENCE.md (Start Here)
**Length**: 11 KB  
**Time to read**: 10 minutes  
**Purpose**: Quick lookup and navigation

Contains:
- Core file locations
- Configuration toggle instructions
- Risk management settings
- Order execution summaries
- Quick troubleshooting
- File absolute paths
- Key code locations table

**Best for**: Quick answers and lookups

---

### 3. PAPER_VS_LIVE_TRADING.md (Detailed Analysis)
**Length**: 26 KB  
**Time to read**: 30-40 minutes  
**Purpose**: Complete technical analysis with code samples

Covers:
1. Where paper trading logic is implemented (lines 179-206)
2. Where live trading logic is implemented (lines 207-239)
3. Key differences between modes
4. Configuration files controlling modes
5. How orders are executed in each mode
6. How positions are tracked
7. Risk management differences (identical in both)
8. Charges and fees calculation
9. Data flow comparison
10. File locations summary
11. Mode switching guide
12. Testing recommendations

**Best for**: Deep technical understanding

---

### 4. ARCHITECTURE_SUMMARY.md (Visual Guide)
**Length**: 21 KB  
**Time to read**: 15-20 minutes  
**Purpose**: Visual diagrams and architecture explanations

Contains:
- System architecture diagram (ASCII)
- Paper trading detailed flow diagram
- Live trading detailed flow diagram
- Order manager state management
- Position tracking schema
- Configuration control points
- Order ID generation details
- Retry logic explanation
- Charge calculation examples
- Safety features comparison table
- Common issues and solutions
- Transition from paper to live

**Best for**: Visual learners and understanding flow

---

## Key Files Referenced

### Configuration
- `/home/user/zerobot/config.py` (215 lines)
  - Line 77: ENABLE_PAPER_TRADING (master toggle)
  - Lines 14-26: Capital settings
  - Lines 76-88: Safety settings

### Implementation
- `/home/user/zerobot/trading_bot.py` (1,888 lines)
  - Lines 157-298: OrderManager class (CRITICAL)
  - Lines 179-206: Paper mode orders
  - Lines 207-239: Live mode orders
  - Lines 90-155: Trade class
  - Lines 300-350: CircuitBreaker class
  - Lines 737-757: Position sizing
  - Lines 783-802: Stop loss validation
  - Lines 770-881: Entry trade logic
  - Lines 925-1021: Exit trade logic
  - Lines 1023-1099: Position monitoring

### Database
- `/home/user/zerobot/database.py` (400+ lines)
  - SQLite schema for trades persistence
  - Trade recording and queries

### Runtime Control
- `/home/user/zerobot/command_handler.py` (244 lines)
  - Emergency stop
  - Position closing
  - Bot control commands

---

## What You'll Learn

### Conceptual Understanding
- How the bot switches between paper and live modes
- Single configuration flag controls everything
- Same strategy logic in both modes
- Only order execution differs

### Technical Understanding
- OrderManager class architecture
- Paper mode: in-memory simulation with PAPER-{timestamp} IDs
- Live mode: Zerodha API with 3 retries and status polling
- Unified position tracking system
- Identical risk management in both modes

### Practical Knowledge
- How to toggle between modes
- Where to find specific implementation
- How to configure risk parameters
- How to monitor positions
- When to use emergency commands

### Implementation Details
- Order ID formats (PAPER- vs real)
- Retry logic (3 attempts, 1 second delay)
- Status polling (2 second intervals, 30 second timeout)
- Charge calculation (6 components)
- Circuit breaker logic (2 triggers)

---

## Quick Facts

### Paper Trading Mode
- **Toggle**: Set `ENABLE_PAPER_TRADING = True` in config.py line 77
- **Order Format**: PAPER-{unix_timestamp_ms}
- **Execution**: Instant (no API calls)
- **Risk**: None
- **Best for**: Testing, learning, strategy validation

### Live Trading Mode
- **Toggle**: Set `ENABLE_PAPER_TRADING = False` in config.py line 77
- **Order Format**: Real Zerodha exchange ID
- **Execution**: API calls with 3 retries, 1 second delay
- **Risk**: Real capital at stake
- **Best for**: After paper trading validation

### Identical Between Modes
- Entry conditions
- Exit conditions
- Risk management
- Position sizing
- Charge calculation
- Database persistence
- Command interface

---

## Reading Recommendations by Role

### For Traders
1. Read: QUICK_REFERENCE.md
2. Read: EXPLORATION_SUMMARY.txt
3. Review: Risk management section in PAPER_VS_LIVE_TRADING.md
4. Test: Paper trading for 5-10 days
5. Then: Switch to live mode

### For Developers
1. Read: PAPER_VS_LIVE_TRADING.md (all)
2. Study: ARCHITECTURE_SUMMARY.md
3. Review: trading_bot.py (OrderManager class)
4. Trace: Code from place_order() to exit_trade()
5. Test: Modify and enhance

### For DevOps/Infrastructure
1. Read: EXPLORATION_SUMMARY.txt
2. Review: config.py (all settings)
3. Check: database.py (SQLite schema)
4. Monitor: logs/trading_bot.log
5. Backup: data/trades.db regularly

### For New Team Members
1. Start: QUICK_REFERENCE.md
2. Then: PAPER_VS_LIVE_TRADING.md (Sections 1-3)
3. Study: ARCHITECTURE_SUMMARY.md
4. Review: Key config parameters
5. Run: Paper trading to understand flow

---

## Documentation Stats

- **Total documentation**: 1,728 lines
- **Files analyzed**: 9 Python files + configuration
- **Code reviewed**: 1,888+ lines (trading_bot.py)
- **Code samples**: 30+ code snippets with line numbers
- **Diagrams**: 4 detailed ASCII architecture diagrams
- **Time to read all**: 60-90 minutes
- **Time to understand fully**: 2-3 hours (includes code review)

---

## Key Takeaway

The bot uses a single configuration flag (`ENABLE_PAPER_TRADING = True/False`) to 
switch between simulated trading and real API orders. Everything else about the 
strategy logic, risk management, and position tracking is identical. The only 
difference is how orders are executed:

- **Paper**: In-memory simulation (instant, no API calls)
- **Live**: Real Zerodha API calls (with retries and status polling)

This design allows safe testing in paper mode before risking real capital in 
live mode, with confidence that the strategy logic is identical.

---

## Starting Point

1. Read `EXPLORATION_SUMMARY.txt` (10 min) - Get overview
2. Read `QUICK_REFERENCE.md` (10 min) - Get specifics
3. Read `PAPER_VS_LIVE_TRADING.md` Sections 1-3 (15 min) - Understand differences
4. Review `config.py` line 77 (2 min) - See the toggle
5. Review `trading_bot.py` lines 179-239 (10 min) - See the implementation

**Total: ~45 minutes to understand everything**

---

## Questions Answered

- Where is paper trading implemented? → Lines 179-206 of trading_bot.py
- Where is live trading implemented? → Lines 207-239 of trading_bot.py
- How do I switch modes? → Change line 77 of config.py
- What are the key differences? → See EXPLORATION_SUMMARY.txt "Key Findings"
- How do orders get executed? → See PAPER_VS_LIVE_TRADING.md Section 5
- How are positions tracked? → See PAPER_VS_LIVE_TRADING.md Section 6
- What about risk management? → See PAPER_VS_LIVE_TRADING.md Section 7
- When should I go live? → See PAPER_VS_LIVE_TRADING.md Section 12

---

Last Updated: November 2, 2025
Documentation Version: 1.0
Status: Complete
