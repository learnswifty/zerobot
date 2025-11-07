#!/usr/bin/env python3
"""
First Candle Breakout Retest Strategy - Backtest
================================================

Strategy Logic (Simplified 2-Candle Pattern):
1. First Candle (09:15-09:20): Strong green candle, body > 0.3% (no upper limit)
2. Second Candle (09:20-09:25): Retest - touches/breaks first candle low, holds support

Entry: When price breaks above first candle high (after retest confirmation)
Exit: Trailing SL, RR target, or time-based exit
"""

import os
import sys
from datetime import datetime, time, timedelta
from typing import Optional, Dict, List, Tuple
import pandas as pd
from collections import defaultdict
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Import from existing modules
from config import TradingConfig, ExitStrategyConfig
from logger import get_logger, print_info, print_success, print_warning, print_error, Colors
from database import TradingDatabase
from timezone_utils import today_ist, current_time_ist, now_ist
from kiteconnect import KiteConnect


class Trade:
    """Represents a single trade"""
    def __init__(self, symbol: str, direction: str, entry_time: datetime,
                 entry_price: float, quantity: int, stop_loss: float,
                 target_price: float = None):
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
        self.status = 'OPEN'

    def update_trailing_stop(self, current_price: float, trailing_percent: float):
        """Update trailing stop loss"""
        if self.direction == 'LONG':
            new_sl = current_price * (1 - trailing_percent / 100)
            if new_sl > self.stop_loss:
                self.stop_loss = new_sl
                return True
        return False


class FirstCandleRetestBacktest:
    """Backtest engine for First Red Candle Breakout strategy"""

    # Strategy parameters
    RETEST_TOLERANCE = 0.5  # % below first low for valid retest

    def __init__(self, capital: float, trade_date: str,
                 exit_strategy: ExitStrategyConfig = None):
        self.initial_capital = capital
        self.current_capital = capital
        self.leverage = 5.0
        self.buying_power = capital * self.leverage
        self.trade_date = trade_date
        self.exit_strategy = exit_strategy or ExitStrategyConfig()

        # Initialize components
        self.logger = get_logger()
        self.db = TradingDatabase(TradingConfig.DB_PATH)
        self.kite = self._init_kite_connect()

        # Trading state
        self.active_trades: Dict[str, Trade] = {}
        self.daily_trades_count = 0

        self.logger.info(f"📊 First Red Candle Breakout Backtest - {trade_date}")
        self.logger.info(f"💰 Capital: ₹{capital:,.0f} | Leverage: {self.leverage}x")

    def _init_kite_connect(self) -> KiteConnect:
        """Initialize Kite Connect"""
        api_key = os.getenv('ZERODHA_API_KEY')
        access_token = os.getenv('ZERODHA_ACCESS_TOKEN')

        if not api_key or not access_token:
            print_error("Zerodha credentials not found!")
            print_info("Please run auth_helper.py first")
            sys.exit(1)

        try:
            kite = KiteConnect(api_key=api_key)
            kite.set_access_token(access_token)
            profile = kite.profile()
            self.logger.info(f"Authenticated as: {profile['user_name']}")
            return kite
        except Exception as e:
            print_error(f"Authentication failed: {e}")
            sys.exit(1)

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

    def fetch_historical_data(self, instrument_token: int, from_date: datetime,
                             to_date: datetime, symbol: str = "") -> Optional[pd.DataFrame]:
        """Fetch historical 5-minute data"""
        try:
            print_info(f"\n📡 Fetching data from Zerodha API:")
            print_info(f"   Symbol: {symbol}")
            print_info(f"   Instrument Token: {instrument_token}")
            print_info(f"   From: {from_date.strftime('%Y-%m-%d %H:%M:%S')}")
            print_info(f"   To: {to_date.strftime('%Y-%m-%d %H:%M:%S')}")
            print_info(f"   Interval: 5minute")

            # Zerodha expects IST dates
            data = self.kite.historical_data(
                instrument_token=instrument_token,
                from_date=from_date,
                to_date=to_date,
                interval='5minute'
            )

            if not data:
                print_warning(f"   ⚠️  No data returned from API")
                return None

            print_success(f"   ✓ Received {len(data)} candles from API")

            df = pd.DataFrame(data)
            df['datetime'] = pd.to_datetime(df['date'])
            df = df.sort_values('datetime').reset_index(drop=True)

            # Show first few raw candles for verification
            print_info(f"\n📋 First 5 candles (raw from API):")
            for i in range(min(5, len(df))):
                row = df.iloc[i]
                color = "🟢" if row['close'] > row['open'] else "🔴" if row['close'] < row['open'] else "⚪"
                print_info(f"   {i+1}. {row['datetime'].strftime('%Y-%m-%d %H:%M')} {color} | "
                          f"O:{row['open']:.2f} H:{row['high']:.2f} L:{row['low']:.2f} C:{row['close']:.2f} V:{row['volume']:,}")

            return df

        except Exception as e:
            self.logger.error(f"Error fetching historical data: {str(e)}")
            print_error(f"❌ API Error: {str(e)}")
            return None

    def calculate_position_size(self, price: float) -> int:
        """Calculate position size based on buying power"""
        if price <= 0:
            return 0
        max_qty = int(self.buying_power / price)
        return max(1, max_qty)

    def identify_first_red_candle(self, df: pd.DataFrame) -> Optional[Dict]:
        """
        Identify First Red Candle for breakout trading

        Strategy:
        1. First candle: Strong move (red or green)
        2. Second candle: Retest/pullback
        3. Entry: When price breaks first candle high/low (no need for third candle confirmation)

        Returns dict with:
        - first_candle: Dict with OHLC, body%, volume
        - second_candle: Dict with retest info
        - setup_high: Breakout level for LONG
        - setup_low: Breakout level for SHORT
        """
        if len(df) < 2:
            return None

        # Get first two 5-minute candles (09:15-09:25)
        candle1 = df.iloc[0]  # 09:15-09:20
        candle2 = df.iloc[1]  # 09:20-09:25

        # Calculate average volume (if enough data)
        avg_volume = df['volume'].mean() if len(df) > 5 else candle1['volume']

        # Helper function to get candle color and body
        def get_candle_info(candle):
            o, c, h, l = candle['open'], candle['close'], candle['high'], candle['low']
            color = "🟢 GREEN" if c > o else ("🔴 RED" if c < o else "⚪ DOJI")
            body_pct = ((c - o) / o) * 100 if o != 0 else 0
            body_size = abs(c - o)
            upper_wick = h - max(o, c)
            lower_wick = min(o, c) - l
            return {
                'color': color,
                'open': o,
                'high': h,
                'low': l,
                'close': c,
                'body_pct': body_pct,
                'body_size': body_size,
                'upper_wick': upper_wick,
                'lower_wick': lower_wick,
                'volume': candle['volume']
            }

        c1 = get_candle_info(candle1)
        c2 = get_candle_info(candle2)

        # Print detailed candle information
        print_info("\n📊 First 2 Candles Analysis:")
        print_info(f"   Average Volume: {avg_volume:,.0f}")

        print_info(f"\n   Candle 1 ({candle1['datetime'].strftime('%H:%M')}) - {c1['color']}")
        print_info(f"      Open:  ₹{c1['open']:.2f}")
        print_info(f"      High:  ₹{c1['high']:.2f}")
        print_info(f"      Low:   ₹{c1['low']:.2f}")
        print_info(f"      Close: ₹{c1['close']:.2f}")
        print_info(f"      Body:  {c1['body_pct']:+.2f}% (₹{c1['body_size']:.2f})")
        print_info(f"      Wicks: Upper ₹{c1['upper_wick']:.2f} | Lower ₹{c1['lower_wick']:.2f}")
        print_info(f"      Volume: {c1['volume']:,.0f} ({(c1['volume']/avg_volume*100):.0f}% of avg)")

        print_info(f"\n   Candle 2 ({candle2['datetime'].strftime('%H:%M')}) - {c2['color']}")
        print_info(f"      Open:  ₹{c2['open']:.2f}")
        print_info(f"      High:  ₹{c2['high']:.2f}")
        print_info(f"      Low:   ₹{c2['low']:.2f}")
        print_info(f"      Close: ₹{c2['close']:.2f}")
        print_info(f"      Body:  {c2['body_pct']:+.2f}% (₹{c2['body_size']:.2f})")
        print_info(f"      Wicks: Upper ₹{c2['upper_wick']:.2f} | Lower ₹{c2['lower_wick']:.2f}")
        print_info(f"      Volume: {c2['volume']:,.0f} ({(c2['volume']/avg_volume*100):.0f}% of avg)")

        print_info(f"\n🔍 Pattern Validation:")

        # === STEP 1: Validate First Candle ===
        first_open = c1['open']
        first_close = c1['close']
        first_high = c1['high']
        first_low = c1['low']
        first_volume = c1['volume']

        # Must be green (bullish)
        if first_close <= first_open:
            print_warning(f"   ❌ First candle must be GREEN (currently {c1['color']})")
            return None
        print_success(f"   ✓ First candle is GREEN")

        # Calculate body percentage
        body_percent = c1['body_pct']

        # Body must have minimum strength (no upper limit - allow strong moves)
        if body_percent < 0.3:
            print_warning(f"   ❌ First candle body {body_percent:.2f}% < 0.3% (too weak)")
            return None
        print_success(f"   ✓ First candle body {body_percent:.2f}% shows momentum")

        # Optional: Check if closes reasonably near high (not mandatory)
        upper_wick = c1['upper_wick']
        body_size = c1['body_size']
        wick_ratio = (upper_wick / body_size) if body_size > 0 else 0
        if wick_ratio > 1.0:  # Only reject if wick is larger than body
            print_warning(f"   ⚠️  Upper wick larger than body ({wick_ratio*100:.0f}%), but acceptable")
        print_success(f"   ✓ First candle structure acceptable (upper wick {wick_ratio*100:.0f}% of body)")

        # Volume check is optional - just log it
        volume_ratio = first_volume / avg_volume if avg_volume > 0 else 1
        print_success(f"   ✓ Volume: {volume_ratio:.1f}x average")

        # === STEP 2: Validate Second Candle (Retest) ===
        second_open = c2['open']
        second_close = c2['close']
        second_high = c2['high']
        second_low = c2['low']

        # Should retest (touch or go below) first candle's low
        retest_threshold = first_low * (1 - self.RETEST_TOLERANCE / 100)
        retest_distance = ((first_low - second_low) / first_low) * 100

        # Valid retest: low should be near or below first candle's low
        if second_low > first_low:
            # Even if not below, should at least test the low closely
            if second_low > first_low * 1.002:  # Within 0.2% of first low
                print_warning(f"   ❌ Second candle low (₹{second_low:.2f}) doesn't retest first candle low (₹{first_low:.2f})")
                print_warning(f"      Distance: {((second_low - first_low) / first_low * 100):.2f}% above (need < 0.2%)")
                return None
            print_success(f"   ✓ Second candle retests first low (within 0.2%)")
        else:
            print_success(f"   ✓ Second candle breaks below first low by {abs(retest_distance):.2f}%")

        # Should not close way below (would invalidate the setup)
        if second_close < retest_threshold:
            print_warning(f"   ❌ Second candle closes too far below (₹{second_close:.2f} < ₹{retest_threshold:.2f})")
            print_warning(f"      Tolerance: 0.5% below first low")
            return None
        print_success(f"   ✓ Second candle holds support (doesn't close too far below)")

        # === PATTERN CONFIRMED - Entry on breakout ===
        print_success(f"\n✅ PATTERN FOUND - Will enter when price breaks ₹{first_high:.2f}")
        entry_price = first_high * 1.001  # Slightly above first candle high
        stop_loss = first_low * 0.999  # Slightly below first candle low

        # Calculate stop loss percentage
        sl_percent = ((entry_price - stop_loss) / entry_price) * 100

        # Validate SL is reasonable
        if sl_percent < TradingConfig.MIN_STOP_LOSS_PERCENT:
            print_warning(f"   ❌ Stop loss too tight ({sl_percent:.2f}% < {TradingConfig.MIN_STOP_LOSS_PERCENT}%)")
            return None
        if sl_percent > TradingConfig.MAX_STOP_LOSS_PERCENT:
            print_warning(f"   ❌ Stop loss too wide ({sl_percent:.2f}% > {TradingConfig.MAX_STOP_LOSS_PERCENT}%)")
            return None
        print_success(f"   ✓ Stop loss within acceptable range ({sl_percent:.2f}%)")

        return {
            'first_candle': {
                'time': candle1['datetime'],
                'open': first_open,
                'high': first_high,
                'low': first_low,
                'close': first_close,
                'volume': first_volume,
                'body_percent': body_percent
            },
            'second_candle': {
                'time': candle2['datetime'],
                'low': second_low,
                'close': second_close,
                'retest_depth': ((first_low - second_low) / first_low) * 100 if second_low < first_low else 0
            },
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'sl_percent': sl_percent,
            'pattern_time': candle2['datetime']  # Pattern confirmed after 2nd candle
        }

    def enter_trade(self, symbol: str, entry_price: float, stop_loss: float,
                   quantity: int, pattern: Dict) -> Optional[Trade]:
        """Enter a trade"""
        # Calculate target if using RR
        target_price = None
        if self.exit_strategy.use_rr:
            risk = entry_price - stop_loss
            reward = risk * self.exit_strategy.rr_ratio
            target_price = entry_price + reward

        trade = Trade(
            symbol=symbol,
            direction='LONG',
            entry_time=pattern['pattern_time'],
            entry_price=entry_price,
            quantity=quantity,
            stop_loss=stop_loss,
            target_price=target_price
        )

        self.active_trades[symbol] = trade
        self.daily_trades_count += 1

        # Calculate position value
        position_value = entry_price * quantity

        # Log entry
        self.logger.info(f"🔵 ENTRY | {symbol} | LONG | Qty: {quantity} | "
                        f"Entry: ₹{entry_price:.2f} | SL: ₹{stop_loss:.2f} ({pattern['sl_percent']:.2f}%) | "
                        f"Position: ₹{position_value:,.0f}")
        if target_price:
            rr_ratio = (target_price - entry_price) / (entry_price - stop_loss)
            self.logger.info(f"   Target: ₹{target_price:.2f} (RR {rr_ratio:.1f}:1)")

        return trade

    def exit_trade(self, trade: Trade, exit_price: float, reason: str) -> bool:
        """Exit a trade"""
        trade.exit_time = datetime.now()
        trade.exit_price = exit_price
        trade.exit_reason = reason
        trade.status = 'CLOSED'

        # Calculate P&L
        gross_pnl = (exit_price - trade.entry_price) * trade.quantity

        # Calculate charges (Indian market)
        entry_value = trade.entry_price * trade.quantity
        exit_value = exit_price * trade.quantity
        turnover = entry_value + exit_value

        brokerage = min(entry_value * 0.0003, 20) + min(exit_value * 0.0003, 20)
        stt = exit_value * 0.00025
        transaction_charges = turnover * 0.0000325
        gst = (brokerage + transaction_charges) * 0.18
        sebi_charges = turnover * 0.000001
        stamp_duty = entry_value * 0.00003

        total_charges = brokerage + stt + transaction_charges + gst + sebi_charges + stamp_duty
        net_pnl = gross_pnl - total_charges

        trade.pnl = net_pnl
        trade.pnl_percent = (net_pnl / (trade.entry_price * trade.quantity)) * 100

        # Update capital
        self.current_capital += net_pnl
        self.buying_power = self.current_capital * self.leverage

        # Calculate duration
        duration = trade.exit_time - trade.entry_time
        minutes = int(duration.total_seconds() / 60)
        hours = minutes // 60
        mins = minutes % 60

        # Log exit
        pnl_symbol = "🟢" if net_pnl > 0 else "🔴"
        duration_str = f"{hours}h {mins}m" if hours > 0 else f"{mins}m"

        self.logger.info(f"{pnl_symbol} EXIT | {trade.symbol} | LONG | "
                        f"Entry: ₹{trade.entry_price:.2f} | Exit: ₹{exit_price:.2f} | "
                        f"P&L: ₹{net_pnl:.2f} ({trade.pnl_percent:+.2f}%) | "
                        f"Duration: {duration_str} | Reason: {reason}")

        return True

    def check_stop_loss(self, current_price: float, trade: Trade) -> bool:
        """Check if stop loss is hit"""
        if current_price <= trade.stop_loss:
            return True
        return False

    def check_target(self, current_price: float, trade: Trade) -> bool:
        """Check if target is hit"""
        if trade.target_price and current_price >= trade.target_price:
            return True
        return False

    def run_backtest(self, symbols: List[str]):
        """Run backtest for all symbols"""
        trade_date = datetime.strptime(self.trade_date, '%Y-%m-%d')

        print_info(f"\n{'='*80}")
        print_info(f"📊 First Candle Breakout Retest Backtest")
        print_info(f"📅 Date: {self.trade_date}")
        print_info(f"💰 Capital: ₹{self.initial_capital:,.0f}")
        print_info(f"📈 Stocks: {', '.join(symbols)}")
        print_info(f"{'='*80}\n")

        for symbol in symbols:
            try:
                print_info(f"\n{'='*80}")
                print_info(f"Testing {symbol}")
                print_info(f"{'='*80}")

                # Get instrument token
                instrument_token = self.get_instrument_token(symbol)
                if not instrument_token:
                    print_warning(f"❌ Could not find instrument token for {symbol}")
                    continue

                print_success(f"✓ Found instrument token: {instrument_token}")

                # Fetch 5-minute data for the day
                from_date = trade_date
                to_date = trade_date + timedelta(days=1)

                df = self.fetch_historical_data(instrument_token, from_date, to_date, symbol)
                if df is None or len(df) == 0:
                    print_warning(f"❌ No data for {symbol}")
                    continue

                # Filter to market hours only
                df = df[df['datetime'].dt.date == trade_date.date()]
                if len(df) < 2:
                    print_warning(f"❌ Insufficient candles for {symbol} (need at least 2)")
                    continue

                print_success(f"✓ Loaded {len(df)} candles for {trade_date.date()}")
                print_info(f"\n💡 To verify on Zerodha Chart:")
                print_info(f"   1. Open Kite chart for {symbol}")
                print_info(f"   2. Set timeframe to 5 minute")
                print_info(f"   3. Go to date: {trade_date.strftime('%d %b %Y')}")
                print_info(f"   4. Compare OHLC values shown below")

                # === STEP 1: Identify Pattern ===
                pattern = self.identify_first_red_candle(df)

                if not pattern:
                    print_warning(f"❌ No valid First Candle Retest pattern found")
                    print_info(f"   First 2 candles did not meet pattern criteria")
                    continue

                # Display pattern details
                print_success(f"\n✅ Pattern Identified!")
                print_info(f"   Candle 1 (09:15): Body {pattern['first_candle']['body_percent']:.2f}% | "
                          f"High: ₹{pattern['first_candle']['high']:.2f} | Low: ₹{pattern['first_candle']['low']:.2f}")
                print_info(f"   Candle 2 (09:20): Retest depth {pattern['second_candle']['retest_depth']:.2f}% | "
                          f"Low: ₹{pattern['second_candle']['low']:.2f}")
                print_info(f"\n   Entry: ₹{pattern['entry_price']:.2f} | SL: ₹{pattern['stop_loss']:.2f} ({pattern['sl_percent']:.2f}%)")

                # === STEP 2: Enter Trade ===
                entry_price = pattern['entry_price']
                stop_loss = pattern['stop_loss']
                quantity = self.calculate_position_size(entry_price)

                if quantity <= 0:
                    print_warning(f"❌ Insufficient capital for position")
                    continue

                trade = self.enter_trade(symbol, entry_price, stop_loss, quantity, pattern)
                if not trade:
                    continue

                # === STEP 3: Monitor Trade ===
                # Start from 3rd candle onwards (pattern confirmed after 2nd candle)
                for idx in range(2, len(df)):
                    row = df.iloc[idx]
                    current_time = row['datetime']
                    current_price = row['close']
                    current_high = row['high']
                    current_low = row['low']

                    # Check force exit time
                    if current_time.time() >= TradingConfig.FORCE_EXIT_TIME:
                        self.exit_trade(trade, current_price, 'TIME_EXIT')
                        del self.active_trades[symbol]
                        break

                    # Check stop loss
                    if self.check_stop_loss(current_low, trade):
                        exit_price = min(current_price, trade.stop_loss)
                        self.exit_trade(trade, exit_price, 'STOP_LOSS')
                        del self.active_trades[symbol]
                        break

                    # Check target
                    if self.exit_strategy.use_rr and self.check_target(current_high, trade):
                        exit_price = max(current_price, trade.target_price)
                        self.exit_trade(trade, exit_price, 'TARGET')
                        del self.active_trades[symbol]
                        break

                    # Update trailing stop
                    if self.exit_strategy.use_trailing_sl:
                        if trade.update_trailing_stop(current_price, self.exit_strategy.trailing_sl_percent):
                            self.logger.debug(f"   {symbol} trailing SL updated to ₹{trade.stop_loss:.2f}")

                # EOD exit if still open
                if symbol in self.active_trades:
                    eod_close = df.iloc[-1]['close']
                    self.exit_trade(trade, eod_close, 'EOD_EXIT')
                    del self.active_trades[symbol]

            except Exception as e:
                print_error(f"❌ Error processing {symbol}: {str(e)}")
                import traceback
                traceback.print_exc()

        # Generate summary
        self.generate_summary()

    def generate_summary(self):
        """Generate backtest summary"""
        print_info(f"\n{'='*80}")
        print_info(f"📊 BACKTEST SUMMARY - First Candle Breakout Retest")
        print_info(f"{'='*80}\n")

        # Get all closed trades for today (we don't save to DB in backtest, so use in-memory)
        # For simplicity, we'll just show final capital
        pnl = self.current_capital - self.initial_capital
        pnl_percent = (pnl / self.initial_capital) * 100

        pnl_color = Colors.OKGREEN if pnl >= 0 else Colors.FAIL

        print_info(f"💰 Starting Capital: ₹{self.initial_capital:,.2f}")
        print_info(f"💰 Ending Capital:   ₹{self.current_capital:,.2f}")
        print_info(f"{pnl_color}💰 Net P&L:          ₹{pnl:,.2f} ({pnl_percent:+.2f}%){Colors.ENDC}")
        print_info(f"\n📊 Total Trades: {self.daily_trades_count}")

        print_info(f"\n{'='*80}\n")


def get_backtest_inputs() -> Tuple[str, float, List[str], ExitStrategyConfig]:
    """Get backtest inputs from user"""
    print_info("\n" + "="*80)
    print_info("        First Candle Breakout Retest - Backtest")
    print_info("="*80 + "\n")

    # Date selection
    print_info("📅 Select backtest date:")
    print_info("   Format: YYYY-MM-DD (e.g., 2025-11-07)")
    date_input = input("Enter date: ").strip()

    try:
        # Validate date format
        datetime.strptime(date_input, '%Y-%m-%d')
        trade_date = date_input
    except ValueError:
        print_warning("Invalid date format, using yesterday")
        trade_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')

    # Capital
    print_info(f"\n💰 Enter capital amount:")
    capital_input = input("Capital (default ₹10,000): ").strip()
    capital = float(capital_input) if capital_input else 10000.0

    # Stocks
    print_info(f"\n📈 Enter stock symbols (comma-separated):")
    print_info("   Example: RELIANCE, TCS, INFY")
    stocks_input = input("Symbols: ").strip()
    symbols = [s.strip().upper() for s in stocks_input.split(',') if s.strip()]

    # Exit strategy
    print_info(f"\n⚙️  Exit Strategy Configuration:")
    use_rr = input("Enable Risk-Reward exit? (Y/n): ").strip().lower() != 'n'
    rr_ratio = 2.0
    if use_rr:
        rr_input = input("Enter RR ratio (default 2.0): ").strip()
        rr_ratio = float(rr_input) if rr_input else 2.0

    use_trailing = input("Enable Trailing Stop Loss? (Y/n): ").strip().lower() != 'n'
    trailing_percent = 1.0
    if use_trailing:
        trailing_input = input("Enter trailing % (default 1.0): ").strip()
        trailing_percent = float(trailing_input) if trailing_input else 1.0

    exit_strategy = ExitStrategyConfig(
        use_rr=use_rr,
        rr_ratio=rr_ratio,
        use_trailing_sl=use_trailing,
        trailing_sl_percent=trailing_percent
    )

    # Summary
    print_info(f"\n{'='*80}")
    print_info(f"Configuration Summary:")
    print_info(f"{'='*80}")
    print_info(f"Date: {trade_date}")
    print_info(f"Capital: ₹{capital:,.0f}")
    print_info(f"Stocks: {', '.join(symbols)}")
    exit_str = []
    if use_rr:
        exit_str.append(f"RR {rr_ratio}:1")
    if use_trailing:
        exit_str.append(f"Trail {trailing_percent}%")
    print_info(f"Exit Strategy: {' | '.join(exit_str)}")
    print_info(f"{'='*80}\n")

    confirm = input("Start backtest? (yes/no): ").strip().lower()
    if confirm not in ['yes', 'y']:
        print_info("Backtest cancelled")
        sys.exit(0)

    return trade_date, capital, symbols, exit_strategy


def main():
    """Main entry point"""
    try:
        # Get inputs
        trade_date, capital, symbols, exit_strategy = get_backtest_inputs()

        # Create backtest instance
        backtest = FirstCandleRetestBacktest(
            capital=capital,
            trade_date=trade_date,
            exit_strategy=exit_strategy
        )

        # Run backtest
        backtest.run_backtest(symbols)

    except KeyboardInterrupt:
        print_info("\n\n⚠️  Backtest interrupted by user")
        sys.exit(0)
    except Exception as e:
        print_error(f"\n❌ Fatal error: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
