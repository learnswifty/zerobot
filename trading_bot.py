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
            self._paper_orders[order_id] = {
                'order_id': order_id,
                'status': 'COMPLETE',
                'tradingsymbol': symbol,
                'transaction_type': transaction_type,
                'quantity': quantity,
                'order_type': order_type,
                'price': price,
                'trigger_price': trigger_price
            }
            self.logger.info(f"[PAPER] Simulated order {order_id} | {symbol} | {transaction_type} {quantity} @ {'₹{:.2f}'.format(price) if price else 'Market'}")
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
        if current_loss >= abs(TradingConfig.CIRCUIT_BREAKER_LOSS_THRESHOLD):
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
                 exit_strategy: ExitStrategyConfig = None):

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
        self.today_date = datetime.now().date().isoformat()
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
        """Fetch historical data"""
        try:
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

    def identify_first_red_candle(self, df: pd.DataFrame) -> Optional[Dict]:
        """Identify the first red candle of the day"""
        today = datetime.now().date()
        df_today = df[df['datetime'].dt.date == today]

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
        max_quantity = int(self.buying_power / price)
        return max(TradingConfig.MIN_POSITION_SIZE, max_quantity)

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

        # Calculate target if using RR
        target_price = None
        if self.exit_strategy.use_rr:
            target_price = self.calculate_target_price(entry_price, stop_loss, direction)

        # Place entry order
        transaction_type = 'BUY' if direction == 'LONG' else 'SELL'

        if TradingConfig.REQUIRE_ORDER_CONFIRMATION:
            print_warning(f"\n{'=' * 60}")
            print_warning(f"ORDER CONFIRMATION REQUIRED")
            print_warning(f"Symbol: {symbol} | Direction: {direction}")
            print_warning(f"Quantity: {quantity} | Price: ₹{entry_price:.2f}")
            print_warning(f"Stop Loss: ₹{stop_loss:.2f} | Target: ₹{target_price:.2f if target_price else 'N/A'}")
            print_warning(f"{'=' * 60}")

            confirm = input(f"{Colors.BOLD}Confirm order? (yes/no): {Colors.ENDC}").strip().lower()
            if confirm not in ['yes', 'y']:
                print_info("Order cancelled by user")
                return None

        order_id = self.order_manager.place_order(symbol, transaction_type, quantity)

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

    def exit_trade(self, trade: Trade, exit_price: float, reason: str):
        """Exit a trade"""

        # Place exit order
        transaction_type = 'SELL' if trade.direction == 'LONG' else 'BUY'
        order_id = self.order_manager.place_order(trade.symbol, transaction_type, trade.quantity)

        if not order_id:
            self.logger.error(f"Failed to place exit order for {trade.symbol}")
            return

        # Wait for order completion
        self.order_manager.wait_for_order_completion(order_id)

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

        # Update capital
        self.current_capital += trade.pnl

        # Remove from active trades
        if trade.symbol in self.active_trades:
            del self.active_trades[trade.symbol]

        # Log trade exit
        self.logger.trade_exit(trade.symbol, trade.direction, trade.quantity,
                              trade.entry_price, trade.exit_price,
                              trade.pnl, reason)

    def monitor_active_trades(self):
        """Monitor and manage active trades"""

        if not self.active_trades:
            return

        # Get quotes for all active stocks
        symbols = list(self.active_trades.keys())

        try:
            quotes = self.kite.quote([f"{TradingConfig.DEFAULT_EXCHANGE}:{s}" for s in symbols])

            for symbol, trade in list(self.active_trades.items()):
                quote_key = f"{TradingConfig.DEFAULT_EXCHANGE}:{symbol}"

                if quote_key not in quotes:
                    continue

                quote = quotes[quote_key]
                ltp = quote['last_price']

                # Update excursions
                trade.update_excursions(ltp)

                # Check stop loss
                if self._check_stop_loss(ltp, trade):
                    self.exit_trade(trade, ltp, 'STOP_LOSS')
                    continue

                # Check target
                if self.exit_strategy.use_rr and self._check_target(ltp, trade):
                    self.exit_trade(trade, ltp, 'TARGET')
                    continue

                # Update trailing stop
                if self.exit_strategy.use_trailing_sl:
                    trade.update_trailing_stop(ltp, self.exit_strategy.trailing_sl_percent)

                    # Update database with new stop loss
                    self.db.update_trade(trade.trade_id, {'stop_loss': trade.stop_loss})

        except Exception as e:
            self.logger.error(f"Error monitoring trades: {str(e)}")

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
        """Force exit all open positions"""
        self.logger.warning(f"Force exiting all positions: {reason}")

        for symbol, trade in list(self.active_trades.items()):
            try:
                # Get current price
                quote = self.kite.quote(f"{TradingConfig.DEFAULT_EXCHANGE}:{symbol}")
                ltp = quote[f"{TradingConfig.DEFAULT_EXCHANGE}:{symbol}"]['last_price']

                self.exit_trade(trade, ltp, reason)
            except Exception as e:
                self.logger.error(f"Error force exiting {symbol}: {str(e)}")

    def generate_daily_summary(self):
        """Generate and save daily summary"""
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
            'max_drawdown': 0  # TODO: Implement drawdown calculation
        }

        self.db.save_daily_summary(summary)
        self.logger.daily_summary(total_trades, winning_trades, losing_trades, 
                                 total_pnl, win_rate)

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
        """Main trading loop"""
        self.is_running = True
        self.monitored_stocks = symbols  # Store monitored stocks
        self.logger.info(f"Starting trading for: {', '.join(symbols)}")

        print_success("\n" + "=" * 80)
        print_success("TRADING BOT IS NOW RUNNING")
        print_success(f"Monitoring {len(symbols)} stocks")
        print_success(f"Capital: ₹{self.current_capital:,.0f} | Buying Power: ₹{self.buying_power:,.0f}")
        print_success("=" * 80 + "\n")

        # Start command handler
        self.command_handler.start_command_listener()

        # Main loop
        while self.is_running:
            try:
                current_time = datetime.now().time()

                # Check if market is open
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

                        # TODO: Implement entry logic
                        # This would check for first red candle breakout
                        pass

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

        # Get user inputs
        capital = get_margin_input()
        leverage = TradingConfig.DEFAULT_LEVERAGE
        print_info(f"Leverage: {leverage}x | Buying Power: ₹{capital * leverage:,.0f}\n")

        stocks = get_stocks_input()
        exit_strategy = get_exit_strategy()

        # Confirm before starting
        print_header("Configuration Summary")
        print(f"Capital: ₹{capital:,.0f}")
        print(f"Leverage: {leverage}x")
        print(f"Buying Power: ₹{capital * leverage:,.0f}")
        print(f"Stocks: {', '.join(stocks)}")
        print(f"Exit Strategy: {exit_strategy}")
        print(f"Paper Trading: {'Yes' if TradingConfig.ENABLE_PAPER_TRADING else 'No'}")

        confirm = input(f"\n{Colors.BOLD}Start trading bot? (yes/no): {Colors.ENDC}").strip().lower()
        if confirm not in ['yes', 'y']:
            print_info("Trading cancelled by user")
            sys.exit(0)

        # Initialize and run bot
        bot = TradingBot(capital=capital, leverage=leverage, exit_strategy=exit_strategy)
        bot.run(stocks)

    except KeyboardInterrupt:
        print_warning("\n\nBot stopped by user")
    except Exception as e:
        print_error(f"\nFatal error: {str(e)}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()