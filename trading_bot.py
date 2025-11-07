#!/usr/bin/env python3
"""
Production-Ready Trading Bot for Zerodha
========================================
First Red Candle Breakout Strategy with Zero-Bug Architecture

Features:
- Configurable capital and leverage
- Multiple exit strategies
- Comprehensive error handling
- Circuit breaker and safety limits
- Real-time monitoring and logging
- Database tracking
- Order management with retries
"""

import os
import sys
import time
from datetime import datetime, timedelta, time as dt_time
from typing import List, Dict, Optional, Tuple, Set
import pandas as pd
import numpy as np
from kiteconnect import KiteConnect
from dotenv import load_dotenv
from collections import defaultdict
import signal

from config import TradingConfig, ExitStrategyConfig
from logger import TradingLogger, get_logger, print_header, print_success, print_error, print_warning, print_info, Colors
from database import TradingDatabase
from command_handler import CommandHandler
from timezone_utils import now_ist, today_ist, current_time_ist, format_ist_datetime, to_naive_ist

# Load environment variables
load_dotenv()


class APIRateLimiter:
    """Rate limiter for API calls to prevent hitting Zerodha limits"""

    def __init__(self, calls_per_second: int = 10, calls_per_minute: int = 200):
        self.calls_per_second = calls_per_second
        self.calls_per_minute = calls_per_minute
        self.second_calls = []  # Timestamps of calls in current second
        self.minute_calls = []  # Timestamps of calls in current minute

    def wait_if_needed(self):
        """Wait if rate limit would be exceeded"""
        current_time = time.time()

        # Clean old timestamps
        self.second_calls = [t for t in self.second_calls if current_time - t < 1.0]
        self.minute_calls = [t for t in self.minute_calls if current_time - t < 60.0]

        # Check per-second limit
        if len(self.second_calls) >= self.calls_per_second:
            sleep_time = 1.0 - (current_time - self.second_calls[0])
            if sleep_time > 0:
                time.sleep(sleep_time)
                current_time = time.time()
                self.second_calls = [t for t in self.second_calls if current_time - t < 1.0]

        # Check per-minute limit
        if len(self.minute_calls) >= self.calls_per_minute:
            sleep_time = 60.0 - (current_time - self.minute_calls[0])
            if sleep_time > 0:
                time.sleep(sleep_time)
                current_time = time.time()
                self.minute_calls = [t for t in self.minute_calls if current_time - t < 60.0]

        # Record this call
        current_time = time.time()
        self.second_calls.append(current_time)
        self.minute_calls.append(current_time)

    def get_stats(self) -> Dict:
        """Get current rate limit statistics"""
        current_time = time.time()
        self.second_calls = [t for t in self.second_calls if current_time - t < 1.0]
        self.minute_calls = [t for t in self.minute_calls if current_time - t < 60.0]

        return {
            'calls_last_second': len(self.second_calls),
            'calls_last_minute': len(self.minute_calls),
            'second_limit': self.calls_per_second,
            'minute_limit': self.calls_per_minute
        }


class Trade:
    """Represents a single trade"""

    def __init__(self, symbol: str, direction: str, entry_time: datetime,
                 entry_price: float, quantity: int, stop_loss: float,
                 target_price: float = None, trade_id: int = None):
        self.trade_id = trade_id
        self.symbol = symbol
        self.direction = direction
        self.entry_time = entry_time
        self.entry_price = entry_price
        self.quantity = quantity
        self.stop_loss = stop_loss
        self.initial_stop_loss = stop_loss
        self.target_price = target_price
        self.exit_time = None
        self.exit_price = None
        self.exit_reason = None
        self.pnl = 0.0
        self.pnl_percent = 0.0
        self.max_favorable_excursion = 0.0
        self.max_adverse_excursion = 0.0
        self.status = 'OPEN'
        self.order_id_entry = None
        self.order_id_exit = None

    def update_trailing_stop(self, current_price: float, trailing_percent: float):
        """Update trailing stop loss"""
        if self.direction == 'LONG':
            new_sl = current_price * (1 - trailing_percent / 100)
            if new_sl > self.stop_loss:
                self.stop_loss = new_sl
        else:  # SHORT
            new_sl = current_price * (1 + trailing_percent / 100)
            if new_sl < self.stop_loss:
                self.stop_loss = new_sl

    def update_excursions(self, current_price: float):
        """Track maximum favorable and adverse price movements"""
        if self.direction == 'LONG':
            move = current_price - self.entry_price
            if move > self.max_favorable_excursion:
                self.max_favorable_excursion = move
            if move < self.max_adverse_excursion:
                self.max_adverse_excursion = move
        else:  # SHORT
            move = self.entry_price - current_price
            if move > self.max_favorable_excursion:
                self.max_favorable_excursion = move
            if move < self.max_adverse_excursion:
                self.max_adverse_excursion = move

    def close_trade(self, exit_time: datetime, exit_price: float, reason: str):
        """Close the trade and calculate P&L"""
        self.exit_time = exit_time
        self.exit_price = exit_price
        self.exit_reason = reason
        self.status = 'CLOSED'

        if self.direction == 'LONG':
            self.pnl = (exit_price - self.entry_price) * self.quantity
            self.pnl_percent = ((exit_price - self.entry_price) / self.entry_price) * 100
        else:  # SHORT
            self.pnl = (self.entry_price - exit_price) * self.quantity
            self.pnl_percent = ((self.entry_price - exit_price) / self.entry_price) * 100


class OrderManager:
    """Handles order placement and management with error handling"""

    def __init__(self, kite: KiteConnect, logger: TradingLogger, rate_limiter: 'APIRateLimiter' = None):
        self.kite = kite
        self.logger = logger
        self.rate_limiter = rate_limiter
        self.retry_count = TradingConfig.API_RETRY_COUNT
        self.retry_delay = TradingConfig.API_RETRY_DELAY
        # Paper trading mode
        self.paper_mode = TradingConfig.ENABLE_PAPER_TRADING
        self._paper_orders = {}

    def place_order(self, symbol: str, transaction_type: str, quantity: int,
                    order_type: str = 'MARKET', price: float = None,
                    trigger_price: float = None) -> Optional[str]:
        """Place an order with retry logic"""
        # Apply rate limiting
        if self.rate_limiter:
            self.rate_limiter.wait_if_needed()

        # Simulate orders in paper trading mode
        if self.paper_mode:
            order_id = f"PAPER-{int(time.time() * 1000)}"
            # For paper trading, use the provided price or fetch current LTP
            actual_price = price
            if actual_price is None and order_type == 'MARKET':
                # For market orders in paper mode, we need to fetch current price
                try:
                    if self.rate_limiter:
                        self.rate_limiter.wait_if_needed()
                    quote = self.kite.quote(f"{TradingConfig.DEFAULT_EXCHANGE}:{symbol}")
                    actual_price = quote[f"{TradingConfig.DEFAULT_EXCHANGE}:{symbol}"]['last_price']
                except:
                    actual_price = 0.0  # Fallback

            self._paper_orders[order_id] = {
                'order_id': order_id,
                'status': 'COMPLETE',
                'tradingsymbol': symbol,
                'transaction_type': transaction_type,
                'quantity': quantity,
                'order_type': order_type,
                'price': actual_price,
                'trigger_price': trigger_price,
                'average_price': actual_price  # Add average price for consistency
            }
            price_str = f"₹{actual_price:.2f}" if actual_price else "Market"
            self.logger.info(f"[PAPER] Simulated order {order_id} | {symbol} | {transaction_type} {quantity} @ {price_str}")
            return order_id

        for attempt in range(self.retry_count):
            try:
                order_params = {
                    'tradingsymbol': symbol,
                    'exchange': TradingConfig.DEFAULT_EXCHANGE,
                    'transaction_type': transaction_type,
                    'quantity': quantity,
                    'order_type': order_type,
                    'product': TradingConfig.ORDER_PRODUCT_TYPE,
                    'validity': TradingConfig.ORDER_VALIDITY
                }

                if price and order_type == 'LIMIT':
                    order_params['price'] = price

                if trigger_price:
                    order_params['trigger_price'] = trigger_price

                # Place order
                order_id = self.kite.place_order(variety=self.kite.VARIETY_REGULAR, **order_params)

                self.logger.order_placed(order_id, symbol, transaction_type, quantity, price)
                return order_id

            except Exception as e:
                self.logger.error(f"Order placement attempt {attempt + 1} failed: {str(e)}")

                if attempt < self.retry_count - 1:
                    time.sleep(self.retry_delay)
                else:
                    self.logger.order_failed(symbol, str(e))
                    return None

    def get_order_status(self, order_id: str) -> Optional[Dict]:
        """Get order status"""
        # Paper mode: instantly complete
        if self.paper_mode:
            return self._paper_orders.get(order_id, {'order_id': order_id, 'status': 'COMPLETE'})

        # Apply rate limiting
        if self.rate_limiter:
            self.rate_limiter.wait_if_needed()

        try:
            orders = self.kite.orders()
            for order in orders:
                if order['order_id'] == order_id:
                    return order
            return None
        except Exception as e:
            self.logger.error(f"Failed to get order status: {str(e)}")
            return None

    def wait_for_order_completion(self, order_id: str, timeout: int = 30) -> bool:
        """Wait for order to complete"""
        # Paper mode: orders are immediately complete
        if self.paper_mode:
            return True
        start_time = time.time()

        while (time.time() - start_time) < timeout:
            status = self.get_order_status(order_id)

            if status:
                if status['status'] == 'COMPLETE':
                    return True
                elif status['status'] in ['REJECTED', 'CANCELLED']:
                    self.logger.error(f"Order {order_id} {status['status']}")
                    return False

            time.sleep(TradingConfig.ORDER_STATUS_CHECK_INTERVAL)

        self.logger.warning(f"Order {order_id} timeout after {timeout}s")
        return False

    def cancel_order(self, order_id: str) -> bool:
        """Cancel an order"""
        if self.paper_mode:
            # Mark as cancelled if tracked
            if order_id in self._paper_orders:
                self._paper_orders[order_id]['status'] = 'CANCELLED'
            self.logger.info(f"[PAPER] Order {order_id} cancelled")
            return True
        try:
            self.kite.cancel_order(variety=self.kite.VARIETY_REGULAR, order_id=order_id)
            self.logger.info(f"Order {order_id} cancelled")
            return True
        except Exception as e:
            self.logger.error(f"Failed to cancel order {order_id}: {str(e)}")
            return False


class CircuitBreaker:
    """Circuit breaker for safety limits"""

    def __init__(self, logger: TradingLogger, db: TradingDatabase):
        self.logger = logger
        self.db = db
        self.enabled = TradingConfig.ENABLE_CIRCUIT_BREAKER
        self.triggered = False
        self.trigger_reason = None

    def check(self, current_capital: float, initial_capital: float,
              consecutive_losses: int, trade_date: str) -> bool:
        """Check if circuit breaker should trigger"""

        if not self.enabled or self.triggered:
            return self.triggered

        # Check daily loss limit
        current_loss = initial_capital - current_capital
        max_loss = initial_capital * (TradingConfig.MAX_DAILY_LOSS_PERCENT / 100)

        if current_loss >= max_loss:
            self.trigger("Daily loss limit exceeded", current_loss)
            return True

        # Check absolute loss threshold
        if current_loss >= TradingConfig.CIRCUIT_BREAKER_LOSS_THRESHOLD:
            self.trigger("Absolute loss threshold exceeded", current_loss)
            return True

        # Check consecutive losses
        if consecutive_losses >= TradingConfig.CIRCUIT_BREAKER_CONSECUTIVE_LOSSES:
            self.trigger(f"{consecutive_losses} consecutive losses", current_loss)
            return True

        return False

    def trigger(self, reason: str, current_loss: float):
        """Trigger circuit breaker"""
        self.triggered = True
        self.trigger_reason = reason
        self.logger.circuit_breaker_triggered(reason, current_loss)
        self.db.log_system_event('CRITICAL', 'CIRCUIT_BREAKER', 
                                f'Triggered: {reason}',
                                {'loss': current_loss})

    def reset(self):
        """Reset circuit breaker"""
        self.triggered = False
        self.trigger_reason = None


class TradingBot:
    """Main trading bot with production-ready features"""

    def __init__(self, capital: float, leverage: float = 5.0,
                 exit_strategy: ExitStrategyConfig = None, trade_date: str = None,
                 top_gainers: List[str] = None):

        # Initialize components
        self.logger = get_logger()
        self.db = TradingDatabase(TradingConfig.DB_PATH)
        self.logger.info(f"📊 Database initialized: {TradingConfig.DB_PATH}")

        # Trading parameters
        self.initial_capital = capital
        self.leverage = leverage
        self.buying_power = capital * leverage
        self.current_capital = capital

        # Exit strategy
        self.exit_strategy = exit_strategy or ExitStrategyConfig()

        # Initialize Kite Connect
        self.kite = self._init_kite_connect()

        # API Rate Limiter (initialize before OrderManager)
        self.rate_limiter = APIRateLimiter(
            calls_per_second=TradingConfig.API_RATE_LIMIT_PER_SECOND,
            calls_per_minute=TradingConfig.API_RATE_LIMIT_PER_MINUTE
        )
        self.logger.info(f"⚡ Rate limiter initialized: {TradingConfig.API_RATE_LIMIT_PER_SECOND}/sec, {TradingConfig.API_RATE_LIMIT_PER_MINUTE}/min")

        # Order manager (pass rate limiter)
        self.order_manager = OrderManager(self.kite, self.logger, self.rate_limiter)

        # Circuit breaker
        self.circuit_breaker = CircuitBreaker(self.logger, self.db)

        # Emergency stop
        self.emergency_stop_triggered = False
        if TradingConfig.EMERGENCY_STOP_ENABLED:
            self.logger.info(f"🚨 Emergency stop enabled - Use 'emergency' command to activate")

        # Command handler for runtime control
        self.command_handler = CommandHandler(self.logger)
        self._setup_command_callbacks()

        # Trading state
        self.active_trades: Dict[str, Trade] = {}
        self.monitored_stocks: List[str] = []  # Track all stocks being monitored
        self.top_gainers: Set[str] = set(top_gainers or [])  # Track Top Gainers stocks (only LONG positions)
        self.today_date = trade_date if trade_date else today_ist().isoformat()
        self.daily_trades_count = 0
        self.stock_entry_count = defaultdict(int)
        self.failed_entry_attempts = defaultdict(int)  # Track consecutive failed entry attempts
        self.last_entry_attempt_time = {}  # Track last attempt time for exponential backoff
        self.is_running = False

        # Setup signal handlers
        self._setup_signal_handlers()

        # Log system start
        self.logger.system_start(self.initial_capital, self.leverage)
        self.db.log_system_event('INFO', 'SYSTEM_START', 
                                f'Capital: ₹{capital:,.0f}, Leverage: {leverage}x')
        if TradingConfig.ENABLE_PAPER_TRADING:
            self.logger.info("[PAPER] Paper trading mode is ENABLED. No live orders will be placed.")

    def _init_kite_connect(self) -> KiteConnect:
        """Initialize and authenticate Kite Connect"""
        api_key = os.getenv('ZERODHA_API_KEY')
        access_token = os.getenv('ZERODHA_ACCESS_TOKEN')

        if not api_key or not access_token:
            print_error("Zerodha credentials not found!")
            print_info("Please run auth_helper.py first")
            sys.exit(1)

        try:
            kite = KiteConnect(api_key=api_key)
            kite.set_access_token(access_token)

            # Verify authentication
            profile = kite.profile()
            self.logger.info(f"Authenticated as: {profile['user_name']} ({profile['user_id']})")
            print_success(f"Authenticated as: {profile['user_name']}")

            return kite

        except Exception as e:
            print_error(f"Authentication failed: {e}")
            print_info("Please run auth_helper.py to refresh your access token")
            sys.exit(1)

    def _setup_signal_handlers(self):
        """Setup handlers for graceful shutdown"""
        def signal_handler(signum, frame):
            self.logger.warning("Shutdown signal received")
            self.shutdown()
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def _setup_command_callbacks(self):
        """Setup command handler callbacks"""
        def handle_add_stock(symbol: str):
            """Add a new stock to monitor"""
            if symbol in self.monitored_stocks:
                print(f"{Colors.WARNING}⚠ {symbol} is already being monitored{Colors.ENDC}")
                self.logger.warning(f"Attempted to add {symbol} but it's already monitored")
                return

            # CRITICAL: Ask if it's a Top Gainer BEFORE adding to monitored_stocks
            # to prevent race condition where trading loop checks the stock before
            # Top Gainer status is set
            print(f"\n{Colors.BOLD}Is {symbol} a Top Gainer stock? (y/n):{Colors.ENDC} ", end='')
            is_top_gainer = False
            try:
                response = input().strip().lower()
                if response in ['y', 'yes']:
                    is_top_gainer = True
                    self.top_gainers.add(symbol)
                    self.logger.info(f"{symbol} marked as Top Gainer (LONG only)")
            except:
                pass

            # Now add to monitored stocks (after Top Gainer status is determined)
            self.monitored_stocks.append(symbol)
            self.logger.info(f"Added {symbol} to monitored stocks")

            # Show confirmation
            if is_top_gainer:
                print(f"{Colors.OKGREEN}✓ {symbol} added as Top Gainer (LONG only){Colors.ENDC}")
            else:
                print(f"{Colors.OKGREEN}✓ {symbol} added as regular stock (LONG & SHORT){Colors.ENDC}")

            print(f"{Colors.OKGREEN}✓ Now monitoring {len(self.monitored_stocks)} stocks{Colors.ENDC}\n")

        def handle_stop_stock(symbol: str):
            if symbol == 'ALL':
                # Stop all monitored stocks
                for s in self.monitored_stocks:
                    self.command_handler.stopped_stocks.add(s)

                # Close any open positions
                for s in list(self.active_trades.keys()):
                    trade = self.active_trades[s]
                    try:
                        if self.rate_limiter:
                            self.rate_limiter.wait_if_needed()
                        quote = self.kite.quote(f"{TradingConfig.DEFAULT_EXCHANGE}:{s}")
                        ltp = quote[f"{TradingConfig.DEFAULT_EXCHANGE}:{s}"]['last_price']
                        self.exit_trade(trade, ltp, "STOPPED_BY_COMMAND")
                    except:
                        pass

                print(f"{Colors.FAIL}🛑 Stopped monitoring all {len(self.monitored_stocks)} stocks{Colors.ENDC}")

            elif symbol in self.active_trades:
                # Close position if exists
                trade = self.active_trades[symbol]
                try:
                    if self.rate_limiter:
                        self.rate_limiter.wait_if_needed()
                    quote = self.kite.quote(f"{TradingConfig.DEFAULT_EXCHANGE}:{symbol}")
                    ltp = quote[f"{TradingConfig.DEFAULT_EXCHANGE}:{symbol}"]['last_price']
                    self.exit_trade(trade, ltp, "STOPPED_BY_COMMAND")
                except:
                    pass

        def handle_resume_stock(symbol: str):
            pass  # Just removes from stopped list

        def handle_status():
            self._show_status()

        def handle_shutdown():
            self.is_running = False

        def handle_emergency_stop():
            # Set emergency stop flag
            self.emergency_stop_triggered = True
            self.logger.critical("Emergency stop triggered!")
            self.db.log_system_event('CRITICAL', 'EMERGENCY_STOP', 'Emergency stop activated via command')

            # Force exit all positions immediately
            self.force_exit_all_positions("EMERGENCY_STOP")

            # Halt all trading
            self.is_running = False

            print(f"\n{Colors.FAIL}🚨 All positions closed. Trading halted.{Colors.ENDC}")
            print(f"{Colors.WARNING}Bot will shutdown in a moment...{Colors.ENDC}\n")

        def handle_exit_position(symbol: str):
            """Exit position for a specific stock"""
            # Validate symbol is monitored
            if symbol not in self.monitored_stocks:
                print(f"{Colors.FAIL}✗ {symbol} is not a monitored stock{Colors.ENDC}")
                if self.monitored_stocks:
                    print(f"  Available stocks: {', '.join(self.monitored_stocks)}")
                self.logger.warning(f"Exit command for unknown stock: {symbol}")
                return

            # Check if position exists
            if symbol not in self.active_trades:
                print(f"{Colors.WARNING}⚠ No active position found for {symbol}{Colors.ENDC}")
                self.logger.warning(f"Exit command for {symbol} - no active position")
                return

            trade = self.active_trades[symbol]
            try:
                # Get current price
                if self.rate_limiter:
                    self.rate_limiter.wait_if_needed()
                quote = self.kite.quote(f"{TradingConfig.DEFAULT_EXCHANGE}:{symbol}")
                ltp = quote[f"{TradingConfig.DEFAULT_EXCHANGE}:{symbol}"]['last_price']

                # Exit the position
                self.logger.info(f"Exiting position for {symbol} via command @ ₹{ltp:.2f}")
                self.exit_trade(trade, ltp, "EXIT_COMMAND")

                print(f"{Colors.OKGREEN}✓ Position closed for {symbol}{Colors.ENDC}")
                print(f"  Exit Price: ₹{ltp:.2f}")
                print(f"  P&L: ₹{trade.pnl:.2f} ({trade.pnl_percent:.2f}%)\n")

            except Exception as e:
                print(f"{Colors.FAIL}✗ Failed to exit position for {symbol}: {str(e)}{Colors.ENDC}")
                self.logger.error(f"Failed to exit position for {symbol} via command: {str(e)}")

        self.command_handler.register_callback('on_add_stock', handle_add_stock)
        self.command_handler.register_callback('on_stop_stock', handle_stop_stock)
        self.command_handler.register_callback('on_resume_stock', handle_resume_stock)
        self.command_handler.register_callback('on_status', handle_status)
        self.command_handler.register_callback('on_shutdown', handle_shutdown)
        self.command_handler.register_callback('on_emergency_stop', handle_emergency_stop)
        self.command_handler.register_callback('on_exit_position', handle_exit_position)

    def is_market_open(self) -> bool:
        """Check if market is currently open"""
        now = current_time_ist()
        return (TradingConfig.MARKET_OPEN_TIME <= now <= TradingConfig.MARKET_CLOSE_TIME)

    def can_take_new_position(self) -> bool:
        """Check if we can take a new position"""
        # Check emergency stop
        if self.emergency_stop_triggered:
            return False

        # Check trading hours
        now = current_time_ist()
        if now > TradingConfig.TRADING_END_TIME:
            return False

        # Check daily trade limit
        if self.daily_trades_count >= TradingConfig.MAX_DAILY_TRADES:
            self.logger.warning(f"Daily trade limit reached: {self.daily_trades_count}")
            return False

        # Check open positions limit
        if len(self.active_trades) >= TradingConfig.MAX_OPEN_POSITIONS:
            self.logger.warning(f"Max open positions reached: {len(self.active_trades)}")
            return False

        # Check circuit breaker
        consecutive_losses = self.db.get_consecutive_losses(self.today_date)
        if self.circuit_breaker.check(self.current_capital, self.initial_capital,
                                     consecutive_losses, self.today_date):
            return False

        return True

    def can_enter_stock(self, symbol: str) -> bool:
        """Check if we can enter a position in this stock"""
        # Check if stock is stopped via command
        if self.command_handler.is_stock_stopped(symbol):
            return False

        # Check if stock already has open position
        if symbol in self.active_trades:
            return False

        # Check exponential backoff for failed attempts
        if symbol in self.failed_entry_attempts and self.failed_entry_attempts[symbol] > 0:
            if symbol in self.last_entry_attempt_time:
                import time
                # Exponential backoff: 30s, 60s, 120s, etc.
                backoff_seconds = min(30 * (2 ** (self.failed_entry_attempts[symbol] - 1)), 300)
                time_since_last = time.time() - self.last_entry_attempt_time[symbol]
                if time_since_last < backoff_seconds:
                    return False  # Still in backoff period

        # Check per-stock entry limit
        entries_today = self.db.get_trade_count_for_stock(symbol, self.today_date)
        if entries_today >= TradingConfig.MAX_ENTRIES_PER_STOCK:
            self.logger.info(f"{symbol} reached max entries for today: {entries_today}")
            return False

        return True

    def get_instrument_token(self, symbol: str) -> Optional[int]:
        """Get instrument token for a symbol"""
        # Apply rate limiting
        if self.rate_limiter:
            self.rate_limiter.wait_if_needed()

        try:
            instruments = self.kite.instruments(TradingConfig.DEFAULT_EXCHANGE)
            for inst in instruments:
                if inst['tradingsymbol'] == symbol and inst['segment'] == TradingConfig.DEFAULT_EXCHANGE:
                    return inst['instrument_token']
            return None
        except Exception as e:
            self.logger.error(f"Error fetching instrument token for {symbol}: {str(e)}")
            return None

    def fetch_historical_data(self, instrument_token: int, days: int = 1) -> Optional[pd.DataFrame]:
        """Fetch historical data - uses trade_date for backtests, current time for live"""
        try:
            # Parse the trade date
            trade_date = datetime.strptime(self.today_date, '%Y-%m-%d')
            today = today_ist()

            # For historical backtests, fetch complete day data
            # For live trading (today), fetch up to current time
            if trade_date.date() < today:
                # Historical backtest - fetch full day (naive datetime, assumed as IST by Kite)
                from_date = trade_date.replace(hour=0, minute=0, second=0)
                to_date = trade_date.replace(hour=23, minute=59, second=59)
            else:
                # Live trading - fetch up to now
                # Convert to naive IST datetime for Kite API
                to_date = to_naive_ist(now_ist())
                from_date = to_date - timedelta(days=days)

            # Apply rate limiting
            if self.rate_limiter:
                self.rate_limiter.wait_if_needed()

            # Kite API expects naive datetime objects in IST
            data = self.kite.historical_data(
                instrument_token=instrument_token,
                from_date=from_date,
                to_date=to_date,
                interval=TradingConfig.INTERVAL
            )

            if not data:
                return None

            df = pd.DataFrame(data)
            df['datetime'] = pd.to_datetime(df['date'])

            # Filter trading hours
            df = df[(df['datetime'].dt.time >= TradingConfig.MARKET_OPEN_TIME) &
                   (df['datetime'].dt.time <= TradingConfig.MARKET_CLOSE_TIME)]

            # Calculate indicators
            if self.exit_strategy.use_ema_exit:
                df['ema'] = df['close'].ewm(span=self.exit_strategy.ema_period, adjust=False).mean()

            if self.exit_strategy.use_atr:
                df['atr'] = self._calculate_atr(df)

            return df

        except Exception as e:
            self.logger.error(f"Error fetching historical data: {str(e)}")
            return None

    def _calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average True Range"""
        high = df['high']
        low = df['low']
        close = df['close']

        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()

        return atr

    def analyze_candle(self, row) -> Dict:
        """Analyze a single candle and return detailed information"""
        open_price = row['open']
        close_price = row['close']
        high_price = row['high']
        low_price = row['low']

        # Determine candle color
        if close_price > open_price:
            color = 'GREEN'
            color_symbol = '🟢'
            body = close_price - open_price
        elif close_price < open_price:
            color = 'RED'
            color_symbol = '🔴'
            body = open_price - close_price
        else:
            color = 'DOJI'
            color_symbol = '⚪'
            body = 0

        # Calculate candle metrics
        total_range = high_price - low_price
        body_percent = (body / total_range * 100) if total_range > 0 else 0

        # Upper and lower shadows
        if color == 'GREEN':
            upper_shadow = high_price - close_price
            lower_shadow = open_price - low_price
        elif color == 'RED':
            upper_shadow = high_price - open_price
            lower_shadow = close_price - low_price
        else:  # DOJI
            upper_shadow = high_price - open_price
            lower_shadow = open_price - low_price

        return {
            'time': row['datetime'],
            'open': open_price,
            'high': high_price,
            'low': low_price,
            'close': close_price,
            'color': color,
            'color_symbol': color_symbol,
            'body': body,
            'body_percent': body_percent,
            'upper_shadow': upper_shadow,
            'lower_shadow': lower_shadow,
            'total_range': total_range
        }

    def display_candle_details(self, candle_info: Dict, show_full: bool = False):
        """Display detailed candle information"""
        time_str = candle_info['time'].strftime('%H:%M')

        if show_full:
            # Full detailed display
            print(f"\n{candle_info['color_symbol']} {time_str} | {candle_info['color']} CANDLE")
            print(f"   Open:  ₹{candle_info['open']:.2f}")
            print(f"   High:  ₹{candle_info['high']:.2f}")
            print(f"   Low:   ₹{candle_info['low']:.2f}")
            print(f"   Close: ₹{candle_info['close']:.2f}")
            print(f"   Body:  ₹{candle_info['body']:.2f} ({candle_info['body_percent']:.1f}%)")
            print(f"   Upper Shadow: ₹{candle_info['upper_shadow']:.2f}")
            print(f"   Lower Shadow: ₹{candle_info['lower_shadow']:.2f}")
        else:
            # Compact display
            print(f"{candle_info['color_symbol']} {time_str} | O:{candle_info['open']:.2f} H:{candle_info['high']:.2f} L:{candle_info['low']:.2f} C:{candle_info['close']:.2f} | {candle_info['color']}")

    def identify_first_red_candle(self, df: pd.DataFrame) -> Optional[Dict]:
        """Identify the first red candle of the day"""
        # Use the trade date (either selected backtest date or today for live trading)
        trade_date = datetime.strptime(self.today_date, '%Y-%m-%d').date()
        df_today = df[df['datetime'].dt.date == trade_date]

        for idx, row in df_today.iterrows():
            if row['close'] < row['open']:  # Red candle
                return {
                    'index': idx,
                    'time': row['datetime'],
                    'high': row['high'],
                    'low': row['low'],
                    'open': row['open'],
                    'close': row['close']
                }
        return None

    def calculate_position_size(self, price: float) -> int:
        """Calculate position size based on buying power"""
        # Validate price
        if price <= 0:
            self.logger.error(f"Invalid price for position sizing: {price}")
            return 0

        # Calculate maximum affordable quantity
        max_quantity = int(self.buying_power / price)

        # Ensure minimum position size
        if max_quantity < TradingConfig.MIN_POSITION_SIZE:
            self.logger.warning(f"Insufficient buying power. Need ₹{price * TradingConfig.MIN_POSITION_SIZE:.2f}, have ₹{self.buying_power:.2f}")
            return 0

        # Apply maximum position size limit if configured
        max_allowed = getattr(TradingConfig, 'MAX_POSITION_SIZE', None)
        if max_allowed and max_quantity > max_allowed:
            max_quantity = max_allowed

        return max_quantity

    def calculate_target_price(self, entry_price: float, stop_loss: float,
                              direction: str) -> float:
        """Calculate target price based on risk-reward ratio"""
        risk = abs(entry_price - stop_loss)
        reward = risk * self.exit_strategy.rr_ratio

        if direction == 'LONG':
            return entry_price + reward
        else:
            return entry_price - reward

    def enter_trade(self, symbol: str, direction: str, entry_price: float,
                   stop_loss: float, quantity: int) -> Optional[Trade]:
        """Enter a new trade"""

        # Validate inputs
        if quantity <= 0:
            self.logger.error(f"Invalid quantity {quantity} for {symbol}")
            return None

        if entry_price <= 0:
            self.logger.error(f"Invalid entry price {entry_price} for {symbol}")
            return None

        # Validate stop loss placement
        if direction == 'LONG':
            if stop_loss >= entry_price:
                self.logger.error(f"Invalid SL for LONG: SL {stop_loss} must be < Entry {entry_price}")
                return None
            sl_percent = ((entry_price - stop_loss) / entry_price) * 100
        else:  # SHORT
            if stop_loss <= entry_price:
                self.logger.error(f"Invalid SL for SHORT: SL {stop_loss} must be > Entry {entry_price}")
                return None
            sl_percent = ((stop_loss - entry_price) / entry_price) * 100

        # Validate stop loss percentage
        if sl_percent < TradingConfig.MIN_STOP_LOSS_PERCENT:
            self.logger.error(f"Stop loss too tight: {sl_percent:.2f}% < {TradingConfig.MIN_STOP_LOSS_PERCENT}%")
            return None

        if sl_percent > TradingConfig.MAX_STOP_LOSS_PERCENT:
            self.logger.error(f"Stop loss too wide: {sl_percent:.2f}% > {TradingConfig.MAX_STOP_LOSS_PERCENT}%")

            # Track failed attempts
            import time
            self.failed_entry_attempts[symbol] += 1
            self.last_entry_attempt_time[symbol] = time.time()

            # After 3 consecutive failures, stop monitoring the stock temporarily
            if self.failed_entry_attempts[symbol] >= 3:
                self.logger.warning(f"{symbol} stopped after {self.failed_entry_attempts[symbol]} failed attempts - stop loss consistently too wide")
                self.command_handler.stopped_stocks.add(symbol)
                print_warning(f"⚠ {symbol} auto-stopped: Stop loss too wide ({sl_percent:.2f}% > {TradingConfig.MAX_STOP_LOSS_PERCENT}%)")

            return None

        # Calculate target if using RR
        target_price = None
        if self.exit_strategy.use_rr:
            target_price = self.calculate_target_price(entry_price, stop_loss, direction)

        # Place entry order
        transaction_type = 'BUY' if direction == 'LONG' else 'SELL'

        if TradingConfig.REQUIRE_ORDER_CONFIRMATION and not TradingConfig.ENABLE_PAPER_TRADING:
            print_warning(f"\n{'=' * 60}")
            print_warning(f"ORDER CONFIRMATION REQUIRED")
            print_warning(f"Symbol: {symbol} | Direction: {direction}")
            print_warning(f"Quantity: {quantity} | Price: ₹{entry_price:.2f}")
            print_warning(f"Stop Loss: ₹{stop_loss:.2f} ({sl_percent:.2f}%) | Target: ₹{target_price:.2f if target_price else 'N/A'}")
            print_warning(f"{'=' * 60}")

            confirm = input(f"{Colors.BOLD}Confirm order? (yes/no): {Colors.ENDC}").strip().lower()
            if confirm not in ['yes', 'y']:
                print_info("Order cancelled by user")
                return None

        order_id = self.order_manager.place_order(symbol, transaction_type, quantity, price=entry_price)

        if not order_id:
            self.logger.error(f"Failed to place entry order for {symbol}")
            return None

        # Wait for order completion
        if not self.order_manager.wait_for_order_completion(order_id):
            self.logger.error(f"Entry order for {symbol} did not complete")
            return None

        # Create trade object
        trade = Trade(
            symbol=symbol,
            direction=direction,
            entry_time=now_ist(),
            entry_price=entry_price,
            quantity=quantity,
            stop_loss=stop_loss,
            target_price=target_price
        )
        trade.order_id_entry = order_id

        # Save to database
        trade_data = {
            'trade_date': self.today_date,
            'symbol': symbol,
            'direction': direction,
            'quantity': quantity,
            'entry_time': trade.entry_time,
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'initial_stop_loss': stop_loss,
            'target_price': target_price,
            'status': 'OPEN',
            'order_id_entry': order_id
        }
        try:
            trade.trade_id = self.db.save_trade(trade_data)
            self.logger.debug(f"✓ Trade saved to database with ID: {trade.trade_id}")
        except Exception as e:
            self.logger.error(f"❌ Failed to save trade to database: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            # Continue anyway - don't fail the trade
            trade.trade_id = None

        # Update state
        self.active_trades[symbol] = trade
        self.daily_trades_count += 1
        self.stock_entry_count[symbol] += 1

        # Reset failed attempts counter on successful entry
        if symbol in self.failed_entry_attempts:
            self.failed_entry_attempts[symbol] = 0

        # Log trade entry
        self.logger.trade_entry(symbol, direction, quantity, entry_price, 
                               stop_loss, target_price)

        return trade

    def calculate_charges(self, entry_price: float, exit_price: float, quantity: int, direction: str) -> Dict[str, float]:
        """Calculate all charges and taxes for a trade (Indian market - NSE intraday)"""

        # Turnover calculation
        buy_value = entry_price * quantity if direction == 'LONG' else exit_price * quantity
        sell_value = exit_price * quantity if direction == 'LONG' else entry_price * quantity
        turnover = buy_value + sell_value

        # 1. Brokerage (assuming 0.03% or ₹20 per order, whichever is lower - typical discount broker)
        brokerage_buy = min(buy_value * 0.0003, 20)
        brokerage_sell = min(sell_value * 0.0003, 20)
        total_brokerage = brokerage_buy + brokerage_sell

        # 2. STT (Securities Transaction Tax) - 0.025% on sell side for intraday equity
        stt = sell_value * 0.00025

        # 3. Transaction charges - NSE: 0.00325% on turnover
        transaction_charges = turnover * 0.0000325

        # 4. GST - 18% on (brokerage + transaction charges)
        gst = (total_brokerage + transaction_charges) * 0.18

        # 5. SEBI charges - ₹10 per crore (₹0.000001 per rupee)
        sebi_charges = turnover * 0.00001

        # 6. Stamp duty - 0.003% on buy side
        stamp_duty = buy_value * 0.00003

        # Total charges
        total_charges = total_brokerage + stt + transaction_charges + gst + sebi_charges + stamp_duty

        return {
            'brokerage': total_brokerage,
            'stt': stt,
            'transaction_charges': transaction_charges,
            'gst': gst,
            'sebi_charges': sebi_charges,
            'stamp_duty': stamp_duty,
            'total_charges': total_charges,
            'turnover': turnover
        }

    def exit_trade(self, trade: Trade, exit_price: float, reason: str) -> bool:
        """Exit a trade and return success status"""

        # Place exit order
        transaction_type = 'SELL' if trade.direction == 'LONG' else 'BUY'
        order_id = self.order_manager.place_order(trade.symbol, transaction_type, trade.quantity, price=exit_price)

        if not order_id:
            self.logger.error(f"Failed to place exit order for {trade.symbol}")
            return False

        # Wait for order completion
        order_success = self.order_manager.wait_for_order_completion(order_id)

        if not order_success:
            self.logger.error(f"Exit order for {trade.symbol} did not complete successfully")
            # Try to cancel the order
            self.order_manager.cancel_order(order_id)
            return False

        # Close trade
        trade.close_trade(now_ist(), exit_price, reason)
        trade.order_id_exit = order_id

        # Calculate charges and net P&L
        charges = self.calculate_charges(trade.entry_price, exit_price, trade.quantity, trade.direction)
        gross_pnl = trade.pnl
        net_pnl = gross_pnl - charges['total_charges']

        # Print detailed trade breakdown
        print(f"\n{Colors.BOLD}{'='*70}{Colors.ENDC}")
        print(f"{Colors.BOLD}📋 TRADE DETAILS - {trade.symbol}{Colors.ENDC}")
        print(f"{Colors.BOLD}{'='*70}{Colors.ENDC}")

        # Entry/Exit Info
        print(f"\n{Colors.OKCYAN}Entry:{Colors.ENDC}")
        print(f"  Direction: {trade.direction}")
        print(f"  Time:      {trade.entry_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Price:     ₹{trade.entry_price:.2f}")
        print(f"  Quantity:  {trade.quantity}")
        print(f"  Value:     ₹{trade.entry_price * trade.quantity:,.2f}")

        print(f"\n{Colors.OKCYAN}Exit:{Colors.ENDC}")
        print(f"  Time:      {trade.exit_time.strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"  Price:     ₹{trade.exit_price:.2f}")
        print(f"  Value:     ₹{trade.exit_price * trade.quantity:,.2f}")
        print(f"  Reason:    {reason}")

        # P&L Breakdown
        pnl_color = Colors.OKGREEN if net_pnl >= 0 else Colors.FAIL
        print(f"\n{Colors.OKCYAN}P&L Breakdown:{Colors.ENDC}")
        print(f"  Gross P&L:           {pnl_color}₹{gross_pnl:,.2f}{Colors.ENDC}")

        # Charges breakdown
        print(f"\n{Colors.WARNING}Charges & Taxes:{Colors.ENDC}")
        print(f"  Brokerage:           ₹{charges['brokerage']:.2f}")
        print(f"  STT:                 ₹{charges['stt']:.2f}")
        print(f"  Transaction Charges: ₹{charges['transaction_charges']:.2f}")
        print(f"  GST (18%):           ₹{charges['gst']:.2f}")
        print(f"  SEBI Charges:        ₹{charges['sebi_charges']:.2f}")
        print(f"  Stamp Duty:          ₹{charges['stamp_duty']:.2f}")
        print(f"  {Colors.BOLD}Total Charges:       ₹{charges['total_charges']:.2f}{Colors.ENDC}")

        print(f"\n{Colors.BOLD}{pnl_color}Net P&L:               ₹{net_pnl:,.2f} ({(net_pnl/(trade.entry_price*trade.quantity))*100:.2f}%){Colors.ENDC}")
        print(f"{Colors.BOLD}{'='*70}{Colors.ENDC}\n")

        # Update database with net P&L
        try:
            self.db.close_trade(
                trade.trade_id,
                trade.exit_time,
                trade.exit_price,
                trade.exit_reason,
                net_pnl,  # Store net P&L instead of gross
                (net_pnl/(trade.entry_price*trade.quantity))*100,  # Net P&L %
                order_id
            )
            self.logger.debug(f"✓ Trade {trade.trade_id} closed in database")
        except Exception as e:
            self.logger.error(f"❌ Failed to close trade in database: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())

        # Update capital AND buying power with net P&L
        self.current_capital += net_pnl
        self.buying_power = self.current_capital * self.leverage

        # Remove from active trades
        if trade.symbol in self.active_trades:
            del self.active_trades[trade.symbol]

        # Log trade exit (using net P&L)
        self.logger.trade_exit(trade.symbol, trade.direction, trade.quantity,
                              trade.entry_price, trade.exit_price,
                              net_pnl, reason)

        return True

    def monitor_active_trades(self):
        """Monitor and manage active trades with robust error handling"""

        if not self.active_trades:
            return

        # Get quotes for all active stocks
        symbols = list(self.active_trades.keys())

        # Retry logic for quote fetching
        max_retries = 3
        retry_count = 0
        quotes = None

        while retry_count < max_retries and quotes is None:
            try:
                # Apply rate limiting
                if self.rate_limiter:
                    self.rate_limiter.wait_if_needed()

                quotes = self.kite.quote([f"{TradingConfig.DEFAULT_EXCHANGE}:{s}" for s in symbols])
                break
            except Exception as e:
                retry_count += 1
                if retry_count < max_retries:
                    self.logger.warning(f"Error fetching quotes (attempt {retry_count}/{max_retries}): {str(e)}")
                    time.sleep(1)  # Wait before retry
                else:
                    self.logger.error(f"Failed to fetch quotes after {max_retries} attempts: {str(e)}")
                    return

        if not quotes:
            self.logger.error("No quotes available for monitoring")
            return

        for symbol, trade in list(self.active_trades.items()):
            try:
                quote_key = f"{TradingConfig.DEFAULT_EXCHANGE}:{symbol}"

                if quote_key not in quotes:
                    self.logger.warning(f"Quote not available for {symbol}, skipping this iteration")
                    continue

                quote = quotes[quote_key]
                ltp = quote['last_price']

                # Update excursions
                trade.update_excursions(ltp)

                # Check stop loss
                if self._check_stop_loss(ltp, trade):
                    exit_success = self.exit_trade(trade, ltp, 'STOP_LOSS')
                    if not exit_success:
                        self.logger.error(f"Failed to exit {symbol} at stop loss, will retry next iteration")
                    continue

                # Check target
                if self.exit_strategy.use_rr and self._check_target(ltp, trade):
                    exit_success = self.exit_trade(trade, ltp, 'TARGET')
                    if not exit_success:
                        self.logger.error(f"Failed to exit {symbol} at target, will retry next iteration")
                    continue

                # Update trailing stop
                if self.exit_strategy.use_trailing_sl:
                    old_sl = trade.stop_loss
                    trade.update_trailing_stop(ltp, self.exit_strategy.trailing_sl_percent)

                    # Only update database if stop loss actually changed
                    if trade.stop_loss != old_sl:
                        self.db.update_trade(trade.trade_id, {'stop_loss': trade.stop_loss})
                        self.logger.info(f"{symbol} trailing SL updated: ₹{old_sl:.2f} -> ₹{trade.stop_loss:.2f}")

            except Exception as e:
                self.logger.error(f"Error monitoring {symbol}: {str(e)}")
                continue

    def _check_stop_loss(self, current_price: float, trade: Trade) -> bool:
        """Check if stop loss is hit"""
        if trade.direction == 'LONG':
            return current_price <= trade.stop_loss
        else:
            return current_price >= trade.stop_loss

    def _check_target(self, current_price: float, trade: Trade) -> bool:
        """Check if target is hit"""
        if not trade.target_price:
            return False

        if trade.direction == 'LONG':
            return current_price >= trade.target_price
        else:
            return current_price <= trade.target_price

    def force_exit_all_positions(self, reason: str = "FORCE_EXIT"):
        """Force exit all open positions with proper cleanup"""
        self.logger.warning(f"Force exiting all positions: {reason}")

        failed_exits = []

        for symbol, trade in list(self.active_trades.items()):
            try:
                # Get current price
                if self.rate_limiter:
                    self.rate_limiter.wait_if_needed()
                quote = self.kite.quote(f"{TradingConfig.DEFAULT_EXCHANGE}:{symbol}")
                ltp = quote[f"{TradingConfig.DEFAULT_EXCHANGE}:{symbol}"]['last_price']

                exit_success = self.exit_trade(trade, ltp, reason)

                if not exit_success:
                    failed_exits.append(symbol)
                    self.logger.error(f"Failed to exit {symbol}, removing from active trades anyway")
                    # Force remove from active trades to prevent orphaned positions
                    if symbol in self.active_trades:
                        del self.active_trades[symbol]

            except Exception as e:
                self.logger.error(f"Error force exiting {symbol}: {str(e)}")
                failed_exits.append(symbol)
                # Force remove from active trades
                if symbol in self.active_trades:
                    del self.active_trades[symbol]

        if failed_exits:
            self.logger.critical(f"Failed to exit positions: {', '.join(failed_exits)}")
            self.logger.critical("MANUAL INTERVENTION REQUIRED - Check broker terminal for actual positions!")
        else:
            self.logger.info(f"Successfully exited all {len(list(self.active_trades.keys()))} positions")

    def generate_daily_summary(self):
        """Generate detailed daily summary with trade-by-trade breakdown"""
        pnl_today = self.current_capital - self.initial_capital
        pnl_percent = (pnl_today / self.initial_capital) * 100
        pnl_color = Colors.OKGREEN if pnl_today >= 0 else Colors.FAIL

        print(f"\n{Colors.BOLD}{'='*100}{Colors.ENDC}")
        print(f"{Colors.BOLD}📊 END OF DAY SUMMARY - {self.today_date}{Colors.ENDC}")
        print(f"{Colors.BOLD}{'='*100}{Colors.ENDC}\n")

        print(f"  Starting Capital:  ₹{self.initial_capital:,.2f}")
        print(f"  Ending Capital:    ₹{self.current_capital:,.2f}")
        print(f"  {Colors.BOLD}{pnl_color}Net P&L:           ₹{pnl_today:,.2f} ({pnl_percent:.2f}%){Colors.ENDC}\n")

        # Get all trades for the day from database
        trades = self.db.get_trades_by_date(self.today_date)

        if not trades:
            print(f"{Colors.WARNING}  No trades executed today{Colors.ENDC}")
            print(f"\n{Colors.BOLD}{'='*100}{Colors.ENDC}\n")
            return

        # Track statistics
        total_trades = 0  # Will count valid trades only
        winning_trades = 0
        losing_trades = 0
        breakeven_trades = 0

        current_streak = 0
        current_streak_type = None
        longest_win_streak = 0
        longest_loss_streak = 0

        # Display trade-by-trade breakdown
        print(f"{Colors.BOLD}{'='*100}{Colors.ENDC}")
        print(f"{Colors.BOLD}TRADE-BY-TRADE BREAKDOWN{Colors.ENDC}")
        print(f"{Colors.BOLD}{'='*100}{Colors.ENDC}\n")

        for idx, trade in enumerate(trades, 1):
            # Validate trade data
            if not trade.get('entry_price') or not trade.get('quantity'):
                print(f"{Colors.WARNING}Trade #{idx} - {trade.get('symbol', 'UNKNOWN')} - SKIPPED (Missing entry data){Colors.ENDC}\n")
                continue

            # Calculate metrics
            entry_value = trade['entry_price'] * trade['quantity']

            # Skip trades with invalid data
            if not entry_value or entry_value == 0:
                print(f"{Colors.WARNING}Trade #{idx} - {trade['symbol']} - SKIPPED (Invalid entry value){Colors.ENDC}\n")
                continue

            if trade['status'] == 'CLOSED':
                # Validate exit data for closed trades
                if not trade.get('exit_price'):
                    print(f"{Colors.WARNING}Trade #{idx} - {trade['symbol']} - SKIPPED (Missing exit price){Colors.ENDC}\n")
                    continue

                gross_pnl = trade['pnl'] if trade['pnl'] else 0

                # Recalculate charges for display
                charges = self.calculate_charges(
                    trade['entry_price'],
                    trade['exit_price'],
                    trade['quantity'],
                    trade['direction']
                )
                total_charges = charges['total_charges']

                # Net P&L should already be in database, but recalculate for accuracy
                if trade['direction'] == 'LONG':
                    gross_profit = (trade['exit_price'] - trade['entry_price']) * trade['quantity']
                else:
                    gross_profit = (trade['entry_price'] - trade['exit_price']) * trade['quantity']

                net_pnl = gross_profit - total_charges
                pnl_pct = (net_pnl / entry_value) * 100 if entry_value else 0
                roi = pnl_pct  # ROI is same as P&L % for intraday trades

                # Track win/loss
                total_trades += 1
                if net_pnl > 0:
                    winning_trades += 1
                    if current_streak_type == 'WIN':
                        current_streak += 1
                    else:
                        current_streak = 1
                        current_streak_type = 'WIN'
                    longest_win_streak = max(longest_win_streak, current_streak)
                elif net_pnl < 0:
                    losing_trades += 1
                    if current_streak_type == 'LOSS':
                        current_streak += 1
                    else:
                        current_streak = 1
                        current_streak_type = 'LOSS'
                    longest_loss_streak = max(longest_loss_streak, current_streak)
                else:
                    breakeven_trades += 1
                    current_streak = 0
                    current_streak_type = None

                # Color coding
                pnl_display_color = Colors.OKGREEN if net_pnl >= 0 else Colors.FAIL

                # Print trade details
                print(f"{Colors.BOLD}Trade #{idx} - {trade['symbol']} ({trade['direction']}){Colors.ENDC}")
                print(f"  Entry:  {trade['entry_time']} @ ₹{trade['entry_price']:.2f} × {trade['quantity']:,} = ₹{entry_value:,.2f}")

                exit_value = trade['exit_price'] * trade['quantity']
                print(f"  Exit:   {trade['exit_time']} @ ₹{trade['exit_price']:.2f} × {trade['quantity']:,} = ₹{exit_value:,.2f}")
                print(f"  Reason: {trade['exit_reason']}")

                print(f"\n  {Colors.BOLD}Performance:{Colors.ENDC}")
                print(f"    Gross P&L:      ₹{gross_profit:,.2f}")
                print(f"    Total Charges:  ₹{total_charges:,.2f}")
                print(f"    {pnl_display_color}Net P&L:        ₹{net_pnl:,.2f} ({pnl_pct:+.2f}%){Colors.ENDC}")
                print(f"    {pnl_display_color}ROI:            {roi:+.2f}%{Colors.ENDC}")

                # Show current streak status for this trade
                if current_streak_type == 'WIN' and net_pnl > 0:
                    streak_color = Colors.OKGREEN
                    print(f"    {streak_color}Win Streak:     {current_streak}{Colors.ENDC}")
                elif current_streak_type == 'LOSS' and net_pnl < 0:
                    streak_color = Colors.FAIL
                    print(f"    {streak_color}Loss Streak:    {current_streak}{Colors.ENDC}")

                print()  # Blank line between trades
            else:
                # Open trade (shouldn't happen in end of day summary, but handle it)
                print(f"{Colors.BOLD}Trade #{idx} - {trade['symbol']} ({trade['direction']}){Colors.ENDC}")
                print(f"  Entry:  {trade['entry_time']} @ ₹{trade['entry_price']:.2f} × {trade['quantity']:,}")
                print(f"  {Colors.WARNING}Status: OPEN (Not closed){Colors.ENDC}\n")

        # Aggregate statistics
        print(f"{Colors.BOLD}{'='*100}{Colors.ENDC}")
        print(f"{Colors.BOLD}AGGREGATE STATISTICS{Colors.ENDC}")
        print(f"{Colors.BOLD}{'='*100}{Colors.ENDC}\n")

        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

        print(f"  Total Trades:          {total_trades}")
        print(f"  {Colors.OKGREEN}Winning Trades:        {winning_trades}{Colors.ENDC}")
        print(f"  {Colors.FAIL}Losing Trades:         {losing_trades}{Colors.ENDC}")
        print(f"  Breakeven Trades:      {breakeven_trades}")
        print(f"  Win Rate:              {win_rate:.1f}%")
        print()
        print(f"  {Colors.OKGREEN}Longest Win Streak:    {longest_win_streak}{Colors.ENDC}")
        print(f"  {Colors.FAIL}Longest Loss Streak:   {longest_loss_streak}{Colors.ENDC}")

        # Current streak at end of day
        if current_streak_type == 'WIN':
            print(f"  {Colors.OKGREEN}Current Streak:        {current_streak} wins{Colors.ENDC}")
        elif current_streak_type == 'LOSS':
            print(f"  {Colors.FAIL}Current Streak:        {current_streak} losses{Colors.ENDC}")
        else:
            print(f"  Current Streak:        None")

        print(f"\n{Colors.BOLD}{'='*100}{Colors.ENDC}\n")

        self.logger.info(f"Day ended - Starting: ₹{self.initial_capital:,.2f} | Ending: ₹{self.current_capital:,.2f} | P&L: ₹{pnl_today:,.2f} | Trades: {total_trades} (W:{winning_trades} L:{losing_trades})")

    def _show_status(self):
        """Show current bot status"""
        print(f"\n{Colors.BOLD}{Colors.OKCYAN}{'=' * 80}{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.OKCYAN}📊 BOT STATUS{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.OKCYAN}{'=' * 80}{Colors.ENDC}")

        # Capital info
        pnl_today = self.current_capital - self.initial_capital
        pnl_color = Colors.OKGREEN if pnl_today >= 0 else Colors.FAIL
        print(f"\n{Colors.BOLD}💰 Capital:{Colors.ENDC}")
        print(f"  Starting: ₹{self.initial_capital:,.2f}")
        print(f"  Current:  ₹{self.current_capital:,.2f}")
        print(f"  P&L:      {pnl_color}₹{pnl_today:,.2f} ({pnl_today/self.initial_capital*100:.2f}%){Colors.ENDC}")
        print(f"  Buying Power: ₹{self.buying_power:,.2f}")

        # Active positions
        print(f"\n{Colors.BOLD}📈 Active Positions: {len(self.active_trades)}{Colors.ENDC}")
        if self.active_trades:
            for symbol, trade in self.active_trades.items():
                try:
                    if self.rate_limiter:
                        self.rate_limiter.wait_if_needed()
                    quote = self.kite.quote(f"{TradingConfig.DEFAULT_EXCHANGE}:{symbol}")
                    ltp = quote[f"{TradingConfig.DEFAULT_EXCHANGE}:{symbol}"]['last_price']
                    unrealized_pnl = (ltp - trade.entry_price) * trade.quantity if trade.direction == 'LONG' else (trade.entry_price - ltp) * trade.quantity
                    pnl_color = Colors.OKGREEN if unrealized_pnl >= 0 else Colors.FAIL
                    print(f"  • {symbol}: {trade.direction} | Entry: ₹{trade.entry_price:.2f} | "
                          f"LTP: ₹{ltp:.2f} | {pnl_color}P&L: ₹{unrealized_pnl:.2f}{Colors.ENDC}")
                except:
                    print(f"  • {symbol}: {trade.direction} | Entry: ₹{trade.entry_price:.2f}")
        else:
            print(f"  {Colors.WARNING}No open positions{Colors.ENDC}")

        # Trade statistics
        print(f"\n{Colors.BOLD}📊 Today's Trades:{Colors.ENDC}")
        trades_today = self.db.get_trades_by_date(self.today_date)
        closed_today = [t for t in trades_today if t['status'] == 'CLOSED']

        if closed_today:
            wins = sum(1 for t in closed_today if t['pnl'] > 0)
            losses = sum(1 for t in closed_today if t['pnl'] < 0)
            win_rate = (wins / len(closed_today) * 100) if closed_today else 0
            print(f"  Total: {len(closed_today)} | Wins: {wins} | Losses: {losses} | Win Rate: {win_rate:.1f}%")
        else:
            print(f"  {Colors.WARNING}No closed trades yet{Colors.ENDC}")

        # Stopped stocks
        print(f"\n{Colors.BOLD}📊 Monitored Stocks:{Colors.ENDC}")
        print(f"  Total: {len(self.monitored_stocks)}")

        active_stocks = [s for s in self.monitored_stocks if s not in self.command_handler.stopped_stocks]
        stopped_stocks = [s for s in self.monitored_stocks if s in self.command_handler.stopped_stocks]

        if active_stocks:
            print(f"  {Colors.OKGREEN}Active: {', '.join(active_stocks)}{Colors.ENDC}")

        if stopped_stocks:
            print(f"  {Colors.FAIL}Stopped: {', '.join(stopped_stocks)}{Colors.ENDC}")

        # Limits
        print(f"\n{Colors.BOLD}⚙️  Limits:{Colors.ENDC}")
        print(f"  Daily Trades: {self.daily_trades_count} / {TradingConfig.MAX_DAILY_TRADES}")
        print(f"  Open Positions: {len(self.active_trades)} / {TradingConfig.MAX_OPEN_POSITIONS}")
        print(f"  Circuit Breaker: {'🔴 TRIGGERED' if self.circuit_breaker.triggered else '🟢 Active'}")

        print(f"\n{Colors.BOLD}{Colors.OKCYAN}{'=' * 80}{Colors.ENDC}\n")

    def shutdown(self):
        """Gracefully shutdown the bot"""
        self.logger.info("Initiating shutdown...")
        self.is_running = False

        # Stop command handler
        self.command_handler.stop()

        # Force exit all positions
        if self.active_trades:
            self.force_exit_all_positions("SHUTDOWN")

        # Generate daily summary
        self.generate_daily_summary()

        # Log shutdown
        self.logger.system_stop("Normal shutdown")
        self.db.log_system_event('INFO', 'SYSTEM_STOP', 'Bot stopped')

    def run(self, symbols: List[str]):
        """Main trading loop - routes to backtest or live based on date"""
        self.is_running = True
        self.monitored_stocks = symbols
        self.logger.info(f"Starting trading for: {', '.join(symbols)}")
        if self.top_gainers:
            self.logger.info(f"Top Gainers (LONG only): {', '.join(self.top_gainers)}")

        print_success("\n" + "=" * 80)
        print_success("TRADING BOT IS NOW RUNNING")
        print_success(f"Monitoring {len(symbols)} stocks")
        if self.top_gainers:
            print_info(f"Top Gainers (LONG only): {', '.join(self.top_gainers)}")
        print_success(f"Capital: ₹{self.current_capital:,.0f} | Buying Power: ₹{self.buying_power:,.0f}")
        print_success("=" * 80 + "\n")

        # Check if historical backtest or live trading
        today = today_ist().isoformat()
        is_historical = self.today_date < today

        if is_historical:
            print_info(f"📊 HISTORICAL BACKTEST MODE - {self.today_date}\n")
            self._run_backtest(symbols)
        else:
            print_info(f"🔴 LIVE TRADING MODE - {self.today_date}\n")
            self._run_live(symbols)

    def _run_backtest(self, symbols: List[str]):
        """Run backtest on historical date - processes all candles with detailed analysis"""
        trade_date = datetime.strptime(self.today_date, '%Y-%m-%d')

        for symbol in symbols:
            try:
                print_info(f"\n{'='*60}")
                print_info(f"Backtesting {symbol} for {self.today_date}")
                print_info(f"{'='*60}")

                # Get data
                instrument_token = self.get_instrument_token(symbol)
                if not instrument_token:
                    continue

                df = self.fetch_historical_data(instrument_token, days=1)
                if df is None or len(df) == 0:
                    print_warning(f"No data for {symbol}")
                    continue

                # Filter to trade date
                df = df[df['datetime'].dt.date == trade_date.date()]
                if len(df) == 0:
                    continue

                print_success(f"Loaded {len(df)} candles for {symbol}\n")

                # Determine setup levels based on config
                if TradingConfig.WAIT_FOR_FIRST_RED_CANDLE:
                    # Find first red candle
                    first_red = self.identify_first_red_candle(df)
                    if not first_red:
                        print_warning("❌ No red candle found - Cannot establish setup")
                        print_info("   Strategy requires first red candle to set high/low levels\n")
                        continue

                    print_success(f"✅ First red candle found at {first_red['time'].strftime('%H:%M')}")
                    print_success(f"   Setup High: ₹{first_red['high']:.2f}")
                    print_success(f"   Setup Low:  ₹{first_red['low']:.2f}\n")

                    setup_high = first_red['high']
                    setup_low = first_red['low']
                    first_red_idx = first_red['index']
                    start_trading_after_idx = first_red_idx
                else:
                    # Use first candle of the day as setup
                    first_candle = df.iloc[0]
                    setup_high = first_candle['high']
                    setup_low = first_candle['low']
                    print_success(f"✅ Using first candle as setup (WAIT_FOR_FIRST_RED_CANDLE=False)")
                    print_success(f"   Setup High: ₹{setup_high:.2f}")
                    print_success(f"   Setup Low:  ₹{setup_low:.2f}\n")
                    start_trading_after_idx = 0

                active_trade = None

                # Process each candle
                for idx in range(len(df)):
                    row = df.iloc[idx]

                    # Skip until after setup candle
                    if idx <= start_trading_after_idx:
                        continue

                    current_time = row['datetime']
                    current_close = row['close']

                    # Time exit
                    if current_time.time() >= TradingConfig.FORCE_EXIT_TIME:
                        if active_trade:
                            print_warning(f"\n⏰ TIME EXIT at {current_time.strftime('%H:%M:%S')}")
                            print_info(f"   Exit: ₹{current_close:.2f} | Entry: ₹{active_trade.entry_price:.2f}")
                            self.exit_trade(active_trade, current_close, 'TIME_EXIT')
                            print_info(f"   P&L: ₹{active_trade.pnl:.2f}\n")
                            active_trade = None  # Clear the trade after exit
                        break

                    # Monitor active trade
                    if active_trade:
                        active_trade.update_excursions(current_close)

                        if self._check_stop_loss(current_close, active_trade):
                            print_error(f"\n🛑 STOP LOSS HIT at {current_time.strftime('%H:%M:%S')}")
                            print_info(f"   Exit: ₹{current_close:.2f} | Entry: ₹{active_trade.entry_price:.2f}")
                            self.exit_trade(active_trade, current_close, 'STOP_LOSS')
                            print_info(f"   P&L: ₹{active_trade.pnl:.2f}\n")
                            active_trade = None
                            continue

                        if self.exit_strategy.use_rr and self._check_target(current_close, active_trade):
                            print_success(f"\n🎯 TARGET HIT at {current_time.strftime('%H:%M:%S')}")
                            print_info(f"   Exit: ₹{current_close:.2f} | Entry: ₹{active_trade.entry_price:.2f}")
                            self.exit_trade(active_trade, current_close, 'TARGET')
                            print_success(f"   P&L: ₹{active_trade.pnl:.2f}\n")
                            active_trade = None
                            continue

                        if self.exit_strategy.use_trailing_sl:
                            old_sl = active_trade.stop_loss
                            active_trade.update_trailing_stop(current_close, self.exit_strategy.trailing_sl_percent)
                            if active_trade.stop_loss != old_sl:
                                self.db.update_trade(active_trade.trade_id, {'stop_loss': active_trade.stop_loss})

                    # Check entries (only if haven't reached max)
                    if not active_trade and self.stock_entry_count[symbol] < TradingConfig.MAX_ENTRIES_PER_STOCK:
                        if current_close > setup_high:
                            quantity = self.calculate_position_size(current_close)
                            if quantity > 0:
                                print_success(f"\n🔵 LONG ENTRY SIGNAL at {current_time.strftime('%H:%M:%S')}")
                                print_info(f"   Entry: ₹{current_close:.2f} | SL: ₹{setup_low:.2f} | Qty: {quantity}")
                                active_trade = self.enter_trade(symbol, 'LONG', current_close, setup_low, quantity)
                                if active_trade:
                                    print_success(f"   ✅ Trade opened successfully\n")

                        elif current_close < setup_low:
                            # Skip SHORT entries for Top Gainers stocks
                            if symbol in self.top_gainers:
                                print_info(f"\n⚠️  SHORT signal skipped for Top Gainer {symbol} at {current_time.strftime('%H:%M:%S')}")
                                print_info(f"   Price: ₹{current_close:.2f} | Top Gainers only take LONG positions\n")
                            else:
                                quantity = self.calculate_position_size(current_close)
                                if quantity > 0:
                                    print_success(f"\n🔴 SHORT ENTRY SIGNAL at {current_time.strftime('%H:%M:%S')}")
                                    print_info(f"   Entry: ₹{current_close:.2f} | SL: ₹{setup_high:.2f} | Qty: {quantity}")
                                    active_trade = self.enter_trade(symbol, 'SHORT', current_close, setup_high, quantity)
                                    if active_trade:
                                        print_success(f"   ✅ Trade opened successfully\n")

                # EOD exit
                if active_trade:
                    eod_time = df.iloc[-1]['datetime']
                    eod_close = df.iloc[-1]['close']
                    print_warning(f"\n📅 END OF DAY EXIT at {eod_time.strftime('%H:%M:%S')}")
                    print_info(f"   Exit: ₹{eod_close:.2f} | Entry: ₹{active_trade.entry_price:.2f}")
                    self.exit_trade(active_trade, eod_close, 'EOD_EXIT')
                    print_info(f"   P&L: ₹{active_trade.pnl:.2f}\n")

            except Exception as e:
                print_error(f"Error: {str(e)}")

        # Summary
        self.generate_daily_summary()
        self.shutdown()

    def _run_live(self, symbols: List[str]):
        """Run live trading loop"""
        self.command_handler.start_command_listener()

        while self.is_running:
            try:
                current_time = current_time_ist()

                if not self.is_market_open():
                    self.logger.info("Market is closed")
                    break

                # Force exit check
                if current_time >= TradingConfig.FORCE_EXIT_TIME:
                    self.force_exit_all_positions("TIME_EXIT")
                    break

                # Monitor active trades
                self.monitor_active_trades()

                # Scan for new opportunities (if allowed)
                if self.can_take_new_position() and current_time < TradingConfig.TRADING_END_TIME:
                    for symbol in list(self.monitored_stocks):  # Use list() to avoid modification during iteration
                        if not self.can_enter_stock(symbol):
                            continue

                        # Implement entry logic - First Red Candle Breakout Strategy
                        try:
                            # Get instrument token
                            instrument_token = self.get_instrument_token(symbol)
                            if not instrument_token:
                                continue

                            # Fetch today's historical data
                            df = self.fetch_historical_data(instrument_token, days=1)
                            if df is None or len(df) < 2:
                                continue

                            # Determine setup levels based on config
                            if TradingConfig.WAIT_FOR_FIRST_RED_CANDLE:
                                # Original strategy: Wait for first red candle
                                first_red = self.identify_first_red_candle(df)
                                if not first_red:
                                    continue
                                setup_high = first_red['high']
                                setup_low = first_red['low']
                            else:
                                # Alternative: Use first candle of the day as setup
                                first_candle = df.iloc[0]
                                setup_high = first_candle['high']
                                setup_low = first_candle['low']
                                self.logger.debug(f"{symbol}: Using first candle levels - High: ₹{setup_high:.2f}, Low: ₹{setup_low:.2f}")

                            # Get current candle (latest data)
                            latest_candle = df.iloc[-1]
                            current_close = latest_candle['close']
                            current_high = latest_candle['high']
                            current_low = latest_candle['low']

                            # Check for LONG breakout signal
                            if current_close > setup_high:
                                # Entry triggered - LONG
                                entry_price = current_close
                                stop_loss = setup_low
                                quantity = self.calculate_position_size(entry_price)

                                if quantity > 0:
                                    self.logger.info(f"LONG signal for {symbol} @ ₹{entry_price:.2f}")
                                    trade = self.enter_trade(symbol, 'LONG', entry_price, stop_loss, quantity)
                                    if trade:
                                        self.logger.info(f"Entered LONG position in {symbol}")
                                    else:
                                        self.logger.warning(f"Failed to enter LONG position in {symbol}")

                            # Check for SHORT breakout signal
                            elif current_close < setup_low:
                                # Skip SHORT entries for Top Gainers stocks
                                if symbol in self.top_gainers:
                                    self.logger.info(f"Skipping SHORT signal for Top Gainer {symbol} @ ₹{current_close:.2f}")
                                else:
                                    # Entry triggered - SHORT
                                    entry_price = current_close
                                    stop_loss = setup_high
                                    quantity = self.calculate_position_size(entry_price)

                                    if quantity > 0:
                                        self.logger.info(f"SHORT signal for {symbol} @ ₹{entry_price:.2f}")
                                        trade = self.enter_trade(symbol, 'SHORT', entry_price, stop_loss, quantity)
                                        if trade:
                                            self.logger.info(f"Entered SHORT position in {symbol}")
                                        else:
                                            self.logger.warning(f"Failed to enter SHORT position in {symbol}")

                        except Exception as e:
                            self.logger.error(f"Error checking entry for {symbol}: {str(e)}")
                            continue

                # Sleep before next iteration
                time.sleep(TradingConfig.QUOTE_UPDATE_INTERVAL)

            except KeyboardInterrupt:
                self.logger.warning("Keyboard interrupt received")
                break
            except Exception as e:
                self.logger.exception("Error in main loop", e)
                time.sleep(5)  # Wait before retrying

        # Shutdown
        self.shutdown()


def get_trading_mode() -> bool:
    """Ask user for paper trading or live trading mode"""
    print_header("Trading Mode Selection")
    print(f"{Colors.BOLD}Choose trading mode:{Colors.ENDC}\n")
    print(f"  {Colors.OKGREEN}1. Paper Trading{Colors.ENDC} - Simulated orders (SAFE, recommended for testing)")
    print(f"  {Colors.FAIL}2. Live Trading{Colors.ENDC}  - Real orders with real money (RISK)")
    print()

    while True:
        choice = input(f"{Colors.BOLD}Enter choice (1/2) [default: 1]: {Colors.ENDC}").strip()

        if not choice or choice == '1':
            print_success("Selected: Paper Trading Mode (Safe)")
            return True  # Paper trading
        elif choice == '2':
            print_warning("\n⚠️  WARNING: LIVE TRADING SELECTED!")
            print_warning("Real money will be used. Real profits and losses will occur.")
            confirm = input(f"\n{Colors.BOLD}Type 'CONFIRM' to proceed with live trading: {Colors.ENDC}").strip()
            if confirm == 'CONFIRM':
                print_error("Selected: Live Trading Mode (Real Money)")
                return False  # Live trading
            else:
                print_info("Live trading not confirmed. Returning to selection...")
                continue
        else:
            print_error("Invalid choice. Please enter 1 or 2.")
            continue


def get_trading_date() -> str:
    """Get trading date for paper trading (only called in paper mode)"""
    print_header("Date Selection (Paper Trading)")
    print(f"{Colors.BOLD}Choose date for paper trading backtest:{Colors.ENDC}\n")
    print(f"  • Press {Colors.OKGREEN}ENTER{Colors.ENDC} for today's date (live paper trading)")
    print(f"  • Enter date in {Colors.OKCYAN}YYYY-MM-DD{Colors.ENDC} format (historical backtest)")
    print(f"\n{Colors.WARNING}Note: Historical dates will fetch past data for backtesting{Colors.ENDC}\n")

    while True:
        date_input = input(f"{Colors.BOLD}Enter date or press ENTER for today: {Colors.ENDC}").strip()

        if not date_input:
            # User pressed Enter - use today
            today = today_ist().isoformat()
            print_success(f"Selected: Today ({today}) - Live paper trading mode")
            return today
        else:
            # Validate date format
            try:
                parsed_date = datetime.strptime(date_input, '%Y-%m-%d')
                selected_date = parsed_date.date().isoformat()

                # Check if date is in the future
                if parsed_date.date() > today_ist():
                    print_error("Cannot select future date. Please choose today or past date.")
                    continue

                # Check if date is too old (optional - limit to 30 days)
                days_ago = (today_ist() - parsed_date.date()).days
                if days_ago > 30:
                    print_warning(f"Warning: Date is {days_ago} days in the past")
                    confirm = input("Historical data may be limited. Continue? (y/n): ").strip().lower()
                    if confirm not in ['y', 'yes']:
                        continue

                print_success(f"Selected: {selected_date} - Historical paper trading (backtest)")
                return selected_date

            except ValueError:
                print_error("Invalid date format. Please use YYYY-MM-DD (e.g., 2025-01-15)")
                continue


def get_margin_input() -> float:
    """Get margin/capital input from user"""
    print_header("Capital Configuration")
    print(f"Default capital: ₹{TradingConfig.DEFAULT_CAPITAL:,.0f}")
    print("Press Enter to use default, or enter custom amount\n")

    margin_input = input(f"{Colors.BOLD}Enter capital amount (or press Enter for ₹10,000): {Colors.ENDC}").strip()

    if not margin_input:
        capital = TradingConfig.DEFAULT_CAPITAL
        print_success(f"Using default capital: ₹{capital:,.0f}")
    else:
        try:
            capital = float(margin_input.replace(',', ''))
            if capital <= 0:
                print_warning("Invalid amount! Using default ₹10,000")
                capital = TradingConfig.DEFAULT_CAPITAL
            else:
                print_success(f"Using capital: ₹{capital:,.0f}")
        except ValueError:
            print_warning("Invalid input! Using default ₹10,000")
            capital = TradingConfig.DEFAULT_CAPITAL

    return capital


def get_stocks_input() -> Tuple[List[str], List[str]]:
    """Get stock symbols from user and identify Top Gainers

    Returns:
        Tuple of (all_stocks, top_gainers_stocks)
    """
    print_header("Stock Selection")
    print("Enter stock symbols (comma-separated)")
    print("Example: RELIANCE, TCS, INFY, HDFCBANK")
    print("Note: Use NSE trading symbols\n")

    stocks_input = input(f"{Colors.BOLD}Enter stock symbols: {Colors.ENDC}").strip()
    stocks = [s.strip().upper() for s in stocks_input.split(',') if s.strip()]

    if not stocks:
        print_error("No stocks entered! Please try again.")
        sys.exit(1)

    print_success(f"Selected {len(stocks)} stocks: {', '.join(stocks)}\n")

    # Ask which stocks are from Top Gainers
    print_info("Top Gainers stocks will only take LONG positions (no short selling)")
    print("Enter Top Gainers stocks (comma-separated), or press Enter to skip:")
    print(f"Available stocks: {', '.join(stocks)}\n")

    top_gainers_input = input(f"{Colors.BOLD}Enter Top Gainers stocks: {Colors.ENDC}").strip()
    top_gainers = []

    if top_gainers_input:
        top_gainers = [s.strip().upper() for s in top_gainers_input.split(',') if s.strip()]
        # Validate that all top gainers are in the main stock list
        invalid_stocks = [s for s in top_gainers if s not in stocks]
        if invalid_stocks:
            print_warning(f"Warning: These stocks are not in your stock list: {', '.join(invalid_stocks)}")
            top_gainers = [s for s in top_gainers if s in stocks]

    if top_gainers:
        print_success(f"Top Gainers (LONG only): {', '.join(top_gainers)}")
        regular_stocks = [s for s in stocks if s not in top_gainers]
        if regular_stocks:
            print_info(f"Regular stocks (LONG & SHORT): {', '.join(regular_stocks)}")
    else:
        print_info("No Top Gainers specified. All stocks can take both LONG and SHORT positions.")

    return stocks, top_gainers


def get_exit_strategy() -> ExitStrategyConfig:
    """Get exit strategy configuration from user"""
    print_header("Exit Strategy Configuration")
    print("Configure exit strategies:\n")

    # Risk-Reward
    use_rr = input(f"{Colors.BOLD}1. Enable Risk-Reward exit? (Y/n): {Colors.ENDC}").strip().lower() != 'n'
    rr_ratio = TradingConfig.DEFAULT_RR_RATIO
    if use_rr:
        rr_input = input(f"   Enter RR ratio (default {TradingConfig.DEFAULT_RR_RATIO}): ").strip()
        rr_ratio = float(rr_input) if rr_input else TradingConfig.DEFAULT_RR_RATIO

    # Trailing SL
    use_trailing = input(f"{Colors.BOLD}2. Enable Trailing Stop Loss? (Y/n): {Colors.ENDC}").strip().lower() != 'n'
    trailing_percent = TradingConfig.DEFAULT_TRAILING_SL_PERCENT
    if use_trailing:
        trailing_input = input(f"   Enter trailing % (default {TradingConfig.DEFAULT_TRAILING_SL_PERCENT}): ").strip()
        trailing_percent = float(trailing_input) if trailing_input else TradingConfig.DEFAULT_TRAILING_SL_PERCENT

    # Time exit (default enabled)
    use_time = True
    exit_time = "14:55"

    strategy = ExitStrategyConfig(
        use_rr=use_rr,
        rr_ratio=rr_ratio,
        use_atr=False,
        use_trailing_sl=use_trailing,
        trailing_sl_percent=trailing_percent,
        use_ema_exit=False,
        use_time_exit=use_time,
        exit_time=exit_time
    )

    print_success(f"\nExit strategy configured: {strategy}")
    return strategy


def main():
    """Main entry point"""
    try:
        print_header("Production Trading Bot - Zerodha")
        print_info(f"Date: {format_ist_datetime()} IST")
        print_info(f"Market Hours: {TradingConfig.MARKET_OPEN_TIME.strftime('%H:%M')} - "
                  f"{TradingConfig.MARKET_CLOSE_TIME.strftime('%H:%M')}\n")

        # Validate configuration
        if not TradingConfig.validate_config():
            print_error("Configuration validation failed!")
            sys.exit(1)

        # Step 1: Ask for trading mode (paper or live)
        is_paper_trading = get_trading_mode()

        # Update config based on user selection
        TradingConfig.ENABLE_PAPER_TRADING = is_paper_trading

        # Step 2: If paper trading, ask for date. If live, use today
        trade_date = None
        if is_paper_trading:
            trade_date = get_trading_date()
        else:
            # Live trading always uses today
            trade_date = today_ist().isoformat()
            print_info(f"Live trading date: {trade_date}\n")

        # Get user inputs
        capital = get_margin_input()
        leverage = TradingConfig.DEFAULT_LEVERAGE
        print_info(f"Leverage: {leverage}x | Buying Power: ₹{capital * leverage:,.0f}\n")

        stocks, top_gainers = get_stocks_input()
        exit_strategy = get_exit_strategy()

        # Confirm before starting
        print_header("Configuration Summary")
        print(f"Trading Mode: {Colors.OKGREEN}Paper Trading{Colors.ENDC}" if is_paper_trading else f"Trading Mode: {Colors.FAIL}LIVE TRADING{Colors.ENDC}")
        print(f"Trading Date: {trade_date}")
        print(f"Capital: ₹{capital:,.0f}")
        print(f"Leverage: {leverage}x")
        print(f"Buying Power: ₹{capital * leverage:,.0f}")
        print(f"Stocks: {', '.join(stocks)}")
        if top_gainers:
            print(f"Top Gainers (LONG only): {', '.join(top_gainers)}")
        print(f"Exit Strategy: {exit_strategy}")

        confirm = input(f"\n{Colors.BOLD}Start trading bot? (yes/no): {Colors.ENDC}").strip().lower()
        if confirm not in ['yes', 'y']:
            print_info("Trading cancelled by user")
            sys.exit(0)

        # Initialize and run bot with trade_date
        bot = TradingBot(capital=capital, leverage=leverage, exit_strategy=exit_strategy,
                        trade_date=trade_date, top_gainers=top_gainers)
        bot.run(stocks)

    except KeyboardInterrupt:
        print_warning("\n\nBot stopped by user")
    except Exception as e:
        print_error(f"\nFatal error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()