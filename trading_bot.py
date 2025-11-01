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
from typing import List, Dict, Optional, Tuple
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

# Load environment variables
load_dotenv()


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

    def __init__(self, kite: KiteConnect, logger: TradingLogger):
        self.kite = kite
        self.logger = logger
        self.retry_count = TradingConfig.API_RETRY_COUNT
        self.retry_delay = TradingConfig.API_RETRY_DELAY
        # Paper trading mode
        self.paper_mode = TradingConfig.ENABLE_PAPER_TRADING
        self._paper_orders = {}

    def place_order(self, symbol: str, transaction_type: str, quantity: int,
                    order_type: str = 'MARKET', price: float = None,
                    trigger_price: float = None) -> Optional[str]:
        """Place an order with retry logic"""
        # Simulate orders in paper trading mode
        if self.paper_mode:
            order_id = f"PAPER-{int(time.time() * 1000)}"
            # For paper trading, use the provided price or fetch current LTP
            actual_price = price
            if actual_price is None and order_type == 'MARKET':
                # For market orders in paper mode, we need to fetch current price
                try:
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
                 exit_strategy: ExitStrategyConfig = None, trade_date: str = None):

        # Initialize components
        self.logger = get_logger()
        self.db = TradingDatabase(TradingConfig.DB_PATH)

        # Trading parameters
        self.initial_capital = capital
        self.leverage = leverage
        self.buying_power = capital * leverage
        self.current_capital = capital

        # Exit strategy
        self.exit_strategy = exit_strategy or ExitStrategyConfig()

        # Initialize Kite Connect
        self.kite = self._init_kite_connect()
        self.order_manager = OrderManager(self.kite, self.logger)

        # Circuit breaker
        self.circuit_breaker = CircuitBreaker(self.logger, self.db)

        # Command handler for runtime control
        self.command_handler = CommandHandler(self.logger)
        self._setup_command_callbacks()

        # Trading state
        self.active_trades: Dict[str, Trade] = {}
        self.monitored_stocks: List[str] = []  # Track all stocks being monitored
        self.today_date = trade_date if trade_date else datetime.now().date().isoformat()
        self.daily_trades_count = 0
        self.stock_entry_count = defaultdict(int)
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
        def handle_stop_stock(symbol: str):
            if symbol == 'ALL':
                # Stop all monitored stocks
                for s in self.monitored_stocks:
                    self.command_handler.stopped_stocks.add(s)

                # Close any open positions
                for s in list(self.active_trades.keys()):
                    trade = self.active_trades[s]
                    try:
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

        self.command_handler.register_callback('on_stop_stock', handle_stop_stock)
        self.command_handler.register_callback('on_resume_stock', handle_resume_stock)
        self.command_handler.register_callback('on_status', handle_status)
        self.command_handler.register_callback('on_shutdown', handle_shutdown)

    def is_market_open(self) -> bool:
        """Check if market is currently open"""
        now = datetime.now().time()
        return (TradingConfig.MARKET_OPEN_TIME <= now <= TradingConfig.MARKET_CLOSE_TIME)

    def can_take_new_position(self) -> bool:
        """Check if we can take a new position"""
        # Check trading hours
        now = datetime.now().time()
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

        # Check per-stock entry limit
        entries_today = self.db.get_trade_count_for_stock(symbol, self.today_date)
        if entries_today >= TradingConfig.MAX_ENTRIES_PER_STOCK:
            self.logger.info(f"{symbol} reached max entries for today: {entries_today}")
            return False

        return True

    def get_instrument_token(self, symbol: str) -> Optional[int]:
        """Get instrument token for a symbol"""
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
            today = datetime.now().date()

            # For historical backtests, fetch complete day data
            # For live trading (today), fetch up to current time
            if trade_date.date() < today:
                # Historical backtest - fetch full day
                from_date = trade_date.replace(hour=0, minute=0, second=0)
                to_date = trade_date.replace(hour=23, minute=59, second=59)
            else:
                # Live trading - fetch up to now
                to_date = datetime.now()
                from_date = to_date - timedelta(days=days)

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
            entry_time=datetime.now(),
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
        trade.trade_id = self.db.save_trade(trade_data)

        # Update state
        self.active_trades[symbol] = trade
        self.daily_trades_count += 1
        self.stock_entry_count[symbol] += 1

        # Log trade entry
        self.logger.trade_entry(symbol, direction, quantity, entry_price, 
                               stop_loss, target_price)

        return trade

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
        trade.close_trade(datetime.now(), exit_price, reason)
        trade.order_id_exit = order_id

        # Update database
        self.db.close_trade(
            trade.trade_id,
            trade.exit_time,
            trade.exit_price,
            trade.exit_reason,
            trade.pnl,
            trade.pnl_percent,
            order_id
        )

        # Update capital AND buying power
        self.current_capital += trade.pnl
        self.buying_power = self.current_capital * self.leverage

        # Remove from active trades
        if trade.symbol in self.active_trades:
            del self.active_trades[trade.symbol]

        # Log trade exit
        self.logger.trade_exit(trade.symbol, trade.direction, trade.quantity,
                              trade.entry_price, trade.exit_price,
                              trade.pnl, reason)

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
        """Generate and save daily summary with drawdown calculation"""
        trades = self.db.get_trades_by_date(self.today_date)

        if not trades:
            self.logger.info("No trades today")
            return

        closed_trades = [t for t in trades if t['status'] == 'CLOSED']

        if not closed_trades:
            self.logger.info("No closed trades today")
            return

        # Calculate statistics
        total_trades = len(closed_trades)
        winning_trades = sum(1 for t in closed_trades if t['pnl'] > 0)
        losing_trades = sum(1 for t in closed_trades if t['pnl'] < 0)
        breakeven_trades = sum(1 for t in closed_trades if t['pnl'] == 0)

        total_pnl = sum(t['pnl'] for t in closed_trades)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0

        wins = [t['pnl'] for t in closed_trades if t['pnl'] > 0]
        losses = [t['pnl'] for t in closed_trades if t['pnl'] < 0]

        avg_win = sum(wins) / len(wins) if wins else 0
        avg_loss = sum(losses) / len(losses) if losses else 0
        largest_win = max(wins) if wins else 0
        largest_loss = min(losses) if losses else 0
        profit_factor = abs(sum(wins) / sum(losses)) if losses and sum(losses) != 0 else 0

        # Calculate maximum drawdown
        max_drawdown = self._calculate_max_drawdown(closed_trades)

        # Save summary
        summary = {
            'trade_date': self.today_date,
            'total_trades': total_trades,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'breakeven_trades': breakeven_trades,
            'total_pnl': total_pnl,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'largest_win': largest_win,
            'largest_loss': largest_loss,
            'profit_factor': profit_factor,
            'starting_capital': self.initial_capital,
            'ending_capital': self.current_capital,
            'max_drawdown': max_drawdown
        }

        self.db.save_daily_summary(summary)
        self.logger.daily_summary(total_trades, winning_trades, losing_trades,
                                 total_pnl, win_rate)

    def _calculate_max_drawdown(self, closed_trades: List[Dict]) -> float:
        """Calculate maximum drawdown from closed trades"""
        if not closed_trades:
            return 0.0

        # Sort trades by exit time
        sorted_trades = sorted(closed_trades, key=lambda t: t['exit_time'])

        # Calculate cumulative P&L curve
        running_capital = self.initial_capital
        peak_capital = running_capital
        max_drawdown = 0.0

        for trade in sorted_trades:
            running_capital += trade['pnl']

            # Update peak
            if running_capital > peak_capital:
                peak_capital = running_capital

            # Calculate drawdown from peak
            drawdown = peak_capital - running_capital

            # Update max drawdown
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        return max_drawdown

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

        print_success("\n" + "=" * 80)
        print_success("TRADING BOT IS NOW RUNNING")
        print_success(f"Monitoring {len(symbols)} stocks")
        print_success(f"Capital: ₹{self.current_capital:,.0f} | Buying Power: ₹{self.buying_power:,.0f}")
        print_success("=" * 80 + "\n")

        # Check if historical backtest or live trading
        today = datetime.now().date().isoformat()
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

                # Display all candles with color analysis
                print_info("📊 CANDLE ANALYSIS (All 5-minute candles):")
                print_info("=" * 60)

                red_candles = []
                green_candles = []
                doji_candles = []

                for idx, row in df.iterrows():
                    candle_info = self.analyze_candle(row)
                    self.display_candle_details(candle_info, show_full=False)

                    # Track candle types
                    if candle_info['color'] == 'RED':
                        red_candles.append(candle_info)
                    elif candle_info['color'] == 'GREEN':
                        green_candles.append(candle_info)
                    else:
                        doji_candles.append(candle_info)

                # Summary
                print_info("\n" + "=" * 60)
                print_info(f"📈 CANDLE SUMMARY:")
                print_success(f"   🟢 Green Candles: {len(green_candles)}")
                print_error(f"   🔴 Red Candles: {len(red_candles)}")
                print_info(f"   ⚪ Doji Candles: {len(doji_candles)}")
                print_info("=" * 60 + "\n")

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
                active_trade = None
                first_red_idx = first_red['index']

                # Process each candle
                for idx in range(len(df)):
                    row = df.iloc[idx]

                    # Skip until after first red
                    if idx <= df.index.get_loc(first_red_idx):
                        continue

                    current_time = row['datetime']
                    current_close = row['close']

                    # Time exit
                    if current_time.time() >= TradingConfig.FORCE_EXIT_TIME:
                        if active_trade:
                            self.exit_trade(active_trade, current_close, 'TIME_EXIT')
                        break

                    # Monitor active trade
                    if active_trade:
                        active_trade.update_excursions(current_close)

                        if self._check_stop_loss(current_close, active_trade):
                            self.exit_trade(active_trade, current_close, 'STOP_LOSS')
                            active_trade = None
                            continue

                        if self.exit_strategy.use_rr and self._check_target(current_close, active_trade):
                            self.exit_trade(active_trade, current_close, 'TARGET')
                            active_trade = None
                            continue

                        if self.exit_strategy.use_trailing_sl:
                            old_sl = active_trade.stop_loss
                            active_trade.update_trailing_stop(current_close, self.exit_strategy.trailing_sl_percent)
                            if active_trade.stop_loss != old_sl:
                                self.db.update_trade(active_trade.trade_id, {'stop_loss': active_trade.stop_loss})

                    # Check entries
                    if not active_trade and self.can_enter_stock(symbol):
                        if current_close > setup_high:
                            quantity = self.calculate_position_size(current_close)
                            if quantity > 0:
                                active_trade = self.enter_trade(symbol, 'LONG', current_close, setup_low, quantity)

                        elif current_close < setup_low:
                            quantity = self.calculate_position_size(current_close)
                            if quantity > 0:
                                active_trade = self.enter_trade(symbol, 'SHORT', current_close, setup_high, quantity)

                # EOD exit
                if active_trade:
                    self.exit_trade(active_trade, df.iloc[-1]['close'], 'EOD_EXIT')

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
                current_time = datetime.now().time()

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
                    for symbol in symbols:
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

                            # Check if we've identified first red candle today
                            first_red = self.identify_first_red_candle(df)
                            if not first_red:
                                continue

                            # Get current candle (latest data)
                            latest_candle = df.iloc[-1]
                            current_close = latest_candle['close']
                            current_high = latest_candle['high']
                            current_low = latest_candle['low']

                            # First red candle levels
                            setup_high = first_red['high']
                            setup_low = first_red['low']

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
            today = datetime.now().date().isoformat()
            print_success(f"Selected: Today ({today}) - Live paper trading mode")
            return today
        else:
            # Validate date format
            try:
                parsed_date = datetime.strptime(date_input, '%Y-%m-%d')
                selected_date = parsed_date.date().isoformat()

                # Check if date is in the future
                if parsed_date.date() > datetime.now().date():
                    print_error("Cannot select future date. Please choose today or past date.")
                    continue

                # Check if date is too old (optional - limit to 30 days)
                days_ago = (datetime.now().date() - parsed_date.date()).days
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


def get_stocks_input() -> List[str]:
    """Get stock symbols from user"""
    print_header("Stock Selection")
    print("Enter stock symbols (comma-separated)")
    print("Example: RELIANCE, TCS, INFY, HDFCBANK")
    print("Note: Use NSE trading symbols\n")

    stocks_input = input(f"{Colors.BOLD}Enter stock symbols: {Colors.ENDC}").strip()
    stocks = [s.strip().upper() for s in stocks_input.split(',') if s.strip()]

    if not stocks:
        print_error("No stocks entered! Please try again.")
        sys.exit(1)

    print_success(f"Selected {len(stocks)} stocks: {', '.join(stocks)}")
    return stocks


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
        print_info(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
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
            trade_date = datetime.now().date().isoformat()
            print_info(f"Live trading date: {trade_date}\n")

        # Get user inputs
        capital = get_margin_input()
        leverage = TradingConfig.DEFAULT_LEVERAGE
        print_info(f"Leverage: {leverage}x | Buying Power: ₹{capital * leverage:,.0f}\n")

        stocks = get_stocks_input()
        exit_strategy = get_exit_strategy()

        # Confirm before starting
        print_header("Configuration Summary")
        print(f"Trading Mode: {Colors.OKGREEN}Paper Trading{Colors.ENDC}" if is_paper_trading else f"Trading Mode: {Colors.FAIL}LIVE TRADING{Colors.ENDC}")
        print(f"Trading Date: {trade_date}")
        print(f"Capital: ₹{capital:,.0f}")
        print(f"Leverage: {leverage}x")
        print(f"Buying Power: ₹{capital * leverage:,.0f}")
        print(f"Stocks: {', '.join(stocks)}")
        print(f"Exit Strategy: {exit_strategy}")

        confirm = input(f"\n{Colors.BOLD}Start trading bot? (yes/no): {Colors.ENDC}").strip().lower()
        if confirm not in ['yes', 'y']:
            print_info("Trading cancelled by user")
            sys.exit(0)

        # Initialize and run bot with trade_date
        bot = TradingBot(capital=capital, leverage=leverage, exit_strategy=exit_strategy, trade_date=trade_date)
        bot.run(stocks)

    except KeyboardInterrupt:
        print_warning("\n\nBot stopped by user")
    except Exception as e:
        print_error(f"\nFatal error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()