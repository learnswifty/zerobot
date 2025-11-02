#!/usr/bin/env python3
"""
Production Trading Bot - Configuration
======================================
All trading parameters, risk limits, and safety configurations
"""

from datetime import time as dt_time
from typing import Dict, Any

class TradingConfig:
    """Main trading configuration"""

    # ==================== CAPITAL & RISK MANAGEMENT ====================
    DEFAULT_CAPITAL = 10000  # Default capital in INR
    DEFAULT_LEVERAGE = 5.0   # Default leverage multiplier

    # Position sizing
    MAX_POSITION_SIZE_PERCENT = 100  # % of buying power per trade
    MIN_POSITION_SIZE = 1            # Minimum quantity

    # Risk limits
    MAX_DAILY_LOSS_PERCENT = 5.0     # Stop trading if 5% daily loss
    MAX_DAILY_TRADES = 10            # Maximum trades per day
    MAX_ENTRIES_PER_STOCK = 2        # Maximum entries per stock per day
    MAX_OPEN_POSITIONS = 5           # Maximum simultaneous positions

    # Stop loss
    MAX_STOP_LOSS_PERCENT = 5.0      # Maximum stop loss per trade
    MIN_STOP_LOSS_PERCENT = 0.5      # Minimum stop loss per trade

    # ==================== STRATEGY PARAMETERS ====================
    INTERVAL = '5minute'             # Candle interval

    # Entry rules
    WAIT_FOR_FIRST_RED_CANDLE = True
    ENTRY_CONFIRMATION_REQUIRED = True

    # Exit strategy defaults
    DEFAULT_RR_RATIO = 2.0           # Risk-reward ratio
    DEFAULT_ATR_MULTIPLIER = 2.0     # ATR multiplier for exits
    DEFAULT_TRAILING_SL_PERCENT = 1.0 # Trailing stop loss %
    DEFAULT_EMA_PERIOD = 10          # EMA period for exits

    # ==================== TRADING HOURS ====================
    MARKET_OPEN_TIME = dt_time(9, 15)    # NSE/BSE opens at 9:15 AM
    MARKET_CLOSE_TIME = dt_time(15, 30)  # NSE/BSE closes at 3:30 PM

    TRADING_START_TIME = dt_time(9, 15)  # Start trading from market open
    TRADING_END_TIME = dt_time(14, 55)   # Stop taking new positions
    FORCE_EXIT_TIME = dt_time(15, 15)    # Force exit all positions

    # ==================== API SETTINGS ====================
    # Zerodha Kite Connect rate limits
    API_RATE_LIMIT_PER_SECOND = 10   # Max requests per second
    API_RATE_LIMIT_PER_MINUTE = 200  # Max requests per minute
    API_RETRY_COUNT = 3              # Number of retries on failure
    API_RETRY_DELAY = 1.0            # Delay between retries (seconds)

    # Data fetch settings
    HISTORICAL_DATA_DAYS = 1         # Days of historical data to fetch
    QUOTE_UPDATE_INTERVAL = 5        # Seconds between quote updates

    # ==================== ORDER SETTINGS ====================
    ORDER_TYPE_DEFAULT = 'MARKET'    # MARKET or LIMIT
    ORDER_PRODUCT_TYPE = 'MIS'       # MIS (intraday) or CNC (delivery)
    ORDER_VALIDITY = 'DAY'           # DAY or IOC

    # Slippage estimation (currently not used in code, reserved for future)
    EXPECTED_SLIPPAGE_PERCENT = 0.05 # Expected slippage %

    # Order timeout
    ORDER_TIMEOUT_SECONDS = 30       # Timeout for order placement
    ORDER_STATUS_CHECK_INTERVAL = 2  # Check order status every N seconds

    # ==================== SAFETY SETTINGS ====================
    ENABLE_PAPER_TRADING = True      # True = Paper trading, False = Live trading
    REQUIRE_ORDER_CONFIRMATION = False # Ask user before placing orders (disable for automated trading)

    # Circuit breaker - Automatic trading halt on excessive losses
    ENABLE_CIRCUIT_BREAKER = True
    CIRCUIT_BREAKER_LOSS_THRESHOLD = 1500  # Stop if loss exceeds ₹1500 (positive number)
    CIRCUIT_BREAKER_CONSECUTIVE_LOSSES = 5  # Stop after N consecutive losses

    # Emergency stop - NOW IMPLEMENTED
    EMERGENCY_STOP_ENABLED = True
    # Use 'emergency' command in the bot's command interface to trigger

    # ==================== MONITORING & ALERTS ====================
    ENABLE_LOGGING = True
    LOG_LEVEL = 'INFO'  # DEBUG, INFO, WARNING, ERROR, CRITICAL
    LOG_TO_FILE = True
    LOG_FILE_PATH = 'logs/trading_bot.log'

    ENABLE_CONSOLE_OUTPUT = True
    ENABLE_TRADE_ALERTS = True

    # Database
    USE_DATABASE = True
    DB_PATH = 'data/trades.db'

    # ==================== STOCK FILTERS ====================
    MIN_STOCK_PRICE = 50.0           # Minimum stock price
    MAX_STOCK_PRICE = 2500.0        # Maximum stock price
    MIN_LIQUIDITY = 100000           # Minimum daily volume

    # Exchange
    DEFAULT_EXCHANGE = 'NSE'
    ALLOWED_EXCHANGES = ['NSE', 'BSE']

    # ==================== ADVANCED FEATURES ====================
    ENABLE_TRAILING_STOP = True
    ENABLE_PARTIAL_EXITS = False     # Feature reserved for future implementation
    ENABLE_POSITION_SCALING = False  # Feature reserved for future implementation

    # Stop Loss Management (CRITICAL for live trading safety)
    USE_EXCHANGE_STOP_LOSS = True    # Place SL orders on exchange (HIGHLY RECOMMENDED for live trading)
    SL_ORDER_TYPE = 'SL-M'           # SL-M (Stop Loss Market) - guaranteed execution
    SL_UPDATE_THRESHOLD_PERCENT = 0.5  # Update exchange SL when trailing moves this % or more

    # Websocket for real-time data (Feature reserved for future implementation)
    USE_WEBSOCKET = False

    @classmethod
    def to_dict(cls) -> Dict[str, Any]:
        """Convert config to dictionary"""
        return {k: v for k, v in cls.__dict__.items() 
                if not k.startswith('_') and not callable(v)}

    @classmethod
    def validate_config(cls) -> bool:
        """Validate configuration parameters"""
        errors = []

        # Validate percentages
        if not (0 < cls.MAX_DAILY_LOSS_PERCENT <= 100):
            errors.append("MAX_DAILY_LOSS_PERCENT must be between 0 and 100")

        if not (0 < cls.MAX_STOP_LOSS_PERCENT <= 100):
            errors.append("MAX_STOP_LOSS_PERCENT must be between 0 and 100")

        # Validate times
        if cls.TRADING_START_TIME >= cls.TRADING_END_TIME:
            errors.append("TRADING_START_TIME must be before TRADING_END_TIME")

        if cls.FORCE_EXIT_TIME <= cls.TRADING_END_TIME:
            errors.append("FORCE_EXIT_TIME must be after TRADING_END_TIME")

        # Validate numbers
        if cls.DEFAULT_CAPITAL <= 0:
            errors.append("DEFAULT_CAPITAL must be positive")

        if cls.DEFAULT_LEVERAGE <= 0:
            errors.append("DEFAULT_LEVERAGE must be positive")

        if errors:
            print("\n❌ Configuration Validation Errors:")
            for error in errors:
                print(f"  - {error}")
            return False

        return True


class ExitStrategyConfig:
    """Exit strategy configuration"""

    def __init__(self,
                 use_rr: bool = True,
                 rr_ratio: float = 2.0,
                 use_atr: bool = False,
                 atr_multiplier: float = 2.0,
                 use_trailing_sl: bool = True,
                 trailing_sl_percent: float = 1.0,
                 use_ema_exit: bool = False,
                 ema_period: int = 10,
                 use_time_exit: bool = True,
                 exit_time: str = "14:55"):

        self.use_rr = use_rr
        self.rr_ratio = rr_ratio
        self.use_atr = use_atr
        self.atr_multiplier = atr_multiplier
        self.use_trailing_sl = use_trailing_sl
        self.trailing_sl_percent = trailing_sl_percent
        self.use_ema_exit = use_ema_exit
        self.ema_period = ema_period
        self.use_time_exit = use_time_exit
        self.exit_time = exit_time

    def __str__(self) -> str:
        """String representation"""
        strategies = []
        if self.use_rr:
            strategies.append(f"RR {self.rr_ratio}:1")
        if self.use_atr:
            strategies.append(f"ATR {self.atr_multiplier}x")
        if self.use_trailing_sl:
            strategies.append(f"Trail {self.trailing_sl_percent}%")
        if self.use_ema_exit:
            strategies.append(f"EMA {self.ema_period}")
        if self.use_time_exit:
            strategies.append(f"Time {self.exit_time}")

        return " | ".join(strategies) if strategies else "No exits"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'use_rr': self.use_rr,
            'rr_ratio': self.rr_ratio,
            'use_atr': self.use_atr,
            'atr_multiplier': self.atr_multiplier,
            'use_trailing_sl': self.use_trailing_sl,
            'trailing_sl_percent': self.trailing_sl_percent,
            'use_ema_exit': self.use_ema_exit,
            'ema_period': self.ema_period,
            'use_time_exit': self.use_time_exit,
            'exit_time': self.exit_time
        }