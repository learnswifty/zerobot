#!/usr/bin/env python3
"""
First Red Candle Breakout Strategy - Enhanced Backtester
========================================================
Production-ready backtesting system with multiple exit strategies

Strategy Rules:
1. Wait for first red candle on 5-minute chart
2. Mark high and low of first red candle
3. Entry: Long when candle closes above high, Short when closes below low
4. Stop Loss: Opposite side of first red candle
5. Multiple Exit Options:
   - Risk-Reward (RR) based: 1:1, 1:2, 1:3 targets
   - ATR-based: Multiple of ATR from entry
   - Trailing Stop Loss: Dynamic stop that trails price
   - EMA 10 crossover: Exit when price crosses EMA 10
   - Time Exit: 2:40 PM
6. Max 2 entries per stock per day

Capital: ₹10,000 with 5x leverage = ₹50,000 buying power
"""

import os
import sys
from datetime import datetime, timedelta, time as dt_time
from typing import List, Dict, Tuple, Optional
import pandas as pd
from kiteconnect import KiteConnect
from dotenv import load_dotenv
import numpy as np
from collections import defaultdict
from tabulate import tabulate

# Load environment variables
load_dotenv()

# ANSI Color Codes
class Colors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKCYAN = '\033[96m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def print_header(text):
    """Print colored header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(80)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * 80}{Colors.ENDC}\n")


def print_success(text):
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")


def print_error(text):
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")


def print_warning(text):
    print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")


def print_info(text):
    print(f"{Colors.OKCYAN}ℹ {text}{Colors.ENDC}")


class ExitStrategy:
    """Configuration for exit strategy"""
    def __init__(self, 
                 use_rr: bool = True,
                 rr_ratio: float = 2.0,
                 use_atr: bool = False,
                 atr_multiplier: float = 2.0,
                 use_trailing_sl: bool = False,
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


class Trade:
    """Represents a single trade with enhanced tracking"""
    def __init__(self, symbol: str, direction: str, entry_time: datetime, 
                 entry_price: float, quantity: int, stop_loss: float, 
                 target_price: float = None):
        self.symbol = symbol
        self.direction = direction  # 'LONG' or 'SHORT'
        self.entry_time = entry_time
        self.entry_price = entry_price
        self.quantity = quantity
        self.stop_loss = stop_loss
        self.initial_stop_loss = stop_loss  # Store original SL
        self.target_price = target_price
        self.exit_time = None
        self.exit_price = None
        self.exit_reason = None
        self.pnl = 0.0
        self.pnl_percent = 0.0
        self.max_favorable_excursion = 0.0  # Best price reached
        self.max_adverse_excursion = 0.0    # Worst price reached

    def update_trailing_stop(self, current_price: float, trailing_percent: float):
        """Update trailing stop loss"""
        if self.direction == 'LONG':
            # For long trades, trail below the price
            new_sl = current_price * (1 - trailing_percent / 100)
            if new_sl > self.stop_loss:
                self.stop_loss = new_sl
        else:  # SHORT
            # For short trades, trail above the price
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

        if self.direction == 'LONG':
            self.pnl = (exit_price - self.entry_price) * self.quantity
            self.pnl_percent = ((exit_price - self.entry_price) / self.entry_price) * 100
        else:  # SHORT
            self.pnl = (self.entry_price - exit_price) * self.quantity
            self.pnl_percent = ((self.entry_price - exit_price) / self.entry_price) * 100

    def to_dict(self):
        """Convert trade to dictionary"""
        return {
            'Symbol': self.symbol,
            'Direction': self.direction,
            'Entry Time': self.entry_time.strftime('%Y-%m-%d %H:%M:%S'),
            'Entry Price': f"₹{self.entry_price:.2f}",
            'Quantity': self.quantity,
            'Stop Loss': f"₹{self.initial_stop_loss:.2f}",
            'Target': f"₹{self.target_price:.2f}" if self.target_price else '-',
            'Exit Time': self.exit_time.strftime('%Y-%m-%d %H:%M:%S') if self.exit_time else 'Open',
            'Exit Price': f"₹{self.exit_price:.2f}" if self.exit_price else '-',
            'Exit Reason': self.exit_reason or '-',
            'P&L': f"₹{self.pnl:.2f}",
            'P&L %': f"{self.pnl_percent:.2f}%",
            'MFE': f"₹{self.max_favorable_excursion:.2f}",
            'MAE': f"₹{self.max_adverse_excursion:.2f}"
        }


class StrategyBacktester:
    """Main backtesting engine with multiple exit strategies"""

    def __init__(self, kite: KiteConnect, capital: float = 10000, leverage: float = 5.0,
                 exit_strategy: ExitStrategy = None):
        self.kite = kite
        self.initial_capital = capital
        self.leverage = leverage
        self.buying_power = capital * leverage
        self.current_capital = capital
        self.trades: List[Trade] = []
        self.max_entries_per_stock = 2
        self.exit_strategy = exit_strategy or ExitStrategy()

    def calculate_atr(self, df: pd.DataFrame, period: int = 14) -> pd.Series:
        """Calculate Average True Range (ATR)"""
        high = df['high']
        low = df['low']
        close = df['close']

        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())

        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(window=period).mean()

        return atr

    def calculate_ema(self, df: pd.DataFrame, period: int = 10) -> pd.Series:
        """Calculate Exponential Moving Average (EMA)"""
        return df['close'].ewm(span=period, adjust=False).mean()

    def get_instrument_token(self, symbol: str, exchange: str = 'NSE') -> Optional[int]:
        """Get instrument token for a symbol"""
        try:
            instruments = self.kite.instruments(exchange)
            for inst in instruments:
                if inst['tradingsymbol'] == symbol and inst['segment'] == exchange:
                    return inst['instrument_token']
            return None
        except Exception as e:
            print_error(f"Error fetching instrument token for {symbol}: {e}")
            return None

    def fetch_historical_data(self, instrument_token: int, from_date: datetime, 
                             to_date: datetime) -> Optional[pd.DataFrame]:
        """Fetch 5-minute historical data with indicators"""
        try:
            # Fetch data
            data = self.kite.historical_data(
                instrument_token=instrument_token,
                from_date=from_date,
                to_date=to_date,
                interval='5minute'
            )

            if not data:
                return None

            # Convert to DataFrame
            df = pd.DataFrame(data)
            df['datetime'] = pd.to_datetime(df['date'])

            # Filter trading hours (9:15 AM to 3:30 PM)
            df = df[(df['datetime'].dt.time >= dt_time(9, 15)) & 
                   (df['datetime'].dt.time <= dt_time(15, 30))]

            # Calculate indicators
            if self.exit_strategy.use_atr:
                df['atr'] = self.calculate_atr(df)

            if self.exit_strategy.use_ema_exit:
                df['ema'] = self.calculate_ema(df, self.exit_strategy.ema_period)

            return df

        except Exception as e:
            print_error(f"Error fetching historical data: {e}")
            return None

    def identify_first_red_candle(self, df: pd.DataFrame) -> Optional[Dict]:
        """Identify the first red candle of the day"""
        for idx, row in df.iterrows():
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
        """Calculate position size based on available capital"""
        # Use 100% of buying power per trade
        max_quantity = int(self.buying_power / price)
        return max(1, max_quantity)  # At least 1 share

    def calculate_target_price(self, entry_price: float, stop_loss: float, 
                              direction: str) -> float:
        """Calculate target price based on risk-reward ratio"""
        risk = abs(entry_price - stop_loss)
        reward = risk * self.exit_strategy.rr_ratio

        if direction == 'LONG':
            return entry_price + reward
        else:  # SHORT
            return entry_price - reward

    def check_stop_loss(self, current_price: float, trade: Trade) -> bool:
        """Check if stop loss is hit"""
        if trade.direction == 'LONG':
            return current_price <= trade.stop_loss
        else:  # SHORT
            return current_price >= trade.stop_loss

    def check_target(self, current_price: float, trade: Trade) -> bool:
        """Check if target is hit"""
        if not trade.target_price:
            return False

        if trade.direction == 'LONG':
            return current_price >= trade.target_price
        else:  # SHORT
            return current_price <= trade.target_price

    def check_atr_exit(self, current_price: float, trade: Trade, atr: float) -> bool:
        """Check if ATR-based exit is triggered"""
        if not self.exit_strategy.use_atr or pd.isna(atr):
            return False

        move_threshold = atr * self.exit_strategy.atr_multiplier

        if trade.direction == 'LONG':
            return (current_price - trade.entry_price) >= move_threshold
        else:  # SHORT
            return (trade.entry_price - current_price) >= move_threshold

    def check_ema_exit(self, current_close: float, ema: float, trade: Trade, 
                       prev_close: float, prev_ema: float) -> bool:
        """Check if EMA crossover exit is triggered"""
        if not self.exit_strategy.use_ema_exit or pd.isna(ema) or pd.isna(prev_ema):
            return False

        if trade.direction == 'LONG':
            # Exit LONG when price crosses below EMA
            return prev_close > prev_ema and current_close < ema
        else:  # SHORT
            # Exit SHORT when price crosses above EMA
            return prev_close < prev_ema and current_close > ema

    def backtest_stock(self, symbol: str, date: datetime) -> List[Trade]:
        """Backtest strategy for a single stock on a single day"""
        print_info(f"Backtesting {symbol} for {date.strftime('%Y-%m-%d')}...")

        # Get instrument token
        instrument_token = self.get_instrument_token(symbol)
        if not instrument_token:
            print_error(f"Could not find instrument token for {symbol}")
            return []

        # Fetch historical data
        from_date = date.replace(hour=0, minute=0, second=0, microsecond=0)
        to_date = date.replace(hour=23, minute=59, second=59, microsecond=0)

        df = self.fetch_historical_data(instrument_token, from_date, to_date)

        if df is None or len(df) == 0:
            print_warning(f"No data available for {symbol} on {date.strftime('%Y-%m-%d')}")
            return []

        print_success(f"Fetched {len(df)} candles for {symbol}")

        # Strategy execution
        stock_trades = []
        first_red = self.identify_first_red_candle(df)

        if not first_red:
            print_warning(f"No red candle found for {symbol}")
            return []

        print_info(f"First red candle at {first_red['time'].strftime('%H:%M:%S')}")
        print_info(f"Range: High={first_red['high']:.2f}, Low={first_red['low']:.2f}")

        # Track setup
        setup_high = first_red['high']
        setup_low = first_red['low']
        entry_count = 0
        active_trade: Optional[Trade] = None

        # Process remaining candles
        first_red_idx = first_red['index']
        df_reset = df.reset_index(drop=True)
        first_red_pos = df_reset[df_reset.index == first_red_idx].index[0]

        for idx in range(first_red_pos + 1, len(df_reset)):
            row = df_reset.iloc[idx]
            current_time = row['datetime']
            current_close = row['close']
            current_high = row['high']
            current_low = row['low']

            # Get previous candle for EMA crossover check
            prev_row = df_reset.iloc[idx - 1] if idx > 0 else None

            # Get ATR if available
            atr = row.get('atr', None)
            ema = row.get('ema', None)
            prev_ema = prev_row.get('ema', None) if prev_row is not None else None
            prev_close = prev_row['close'] if prev_row is not None else None

            # Time exit check
            if self.exit_strategy.use_time_exit:
                hour, minute = map(int, self.exit_strategy.exit_time.split(':'))
                exit_time = dt_time(hour, minute)
                if current_time.time() >= exit_time:
                    if active_trade:
                        active_trade.close_trade(current_time, current_close, 'TIME_EXIT')
                        stock_trades.append(active_trade)
                        active_trade = None
                    break

            # Manage active trade
            if active_trade:
                # Update excursions
                active_trade.update_excursions(current_close)

                # Update trailing stop loss
                if self.exit_strategy.use_trailing_sl:
                    active_trade.update_trailing_stop(current_close, 
                                                     self.exit_strategy.trailing_sl_percent)

                # Check exits in priority order
                exit_triggered = False
                exit_reason = None
                exit_price = current_close

                # 1. Stop Loss (highest priority)
                if self.check_stop_loss(current_close, active_trade):
                    exit_triggered = True
                    exit_reason = 'STOP_LOSS'
                    exit_price = active_trade.stop_loss

                # 2. Target (RR-based)
                elif self.exit_strategy.use_rr and self.check_target(current_close, active_trade):
                    exit_triggered = True
                    exit_reason = f'TARGET_RR_{self.exit_strategy.rr_ratio}'
                    exit_price = active_trade.target_price

                # 3. ATR-based exit
                elif self.check_atr_exit(current_close, active_trade, atr):
                    exit_triggered = True
                    exit_reason = f'ATR_EXIT_{self.exit_strategy.atr_multiplier}x'

                # 4. EMA crossover exit
                elif self.check_ema_exit(current_close, ema, active_trade, prev_close, prev_ema):
                    exit_triggered = True
                    exit_reason = f'EMA_{self.exit_strategy.ema_period}_CROSS'

                if exit_triggered:
                    active_trade.close_trade(current_time, exit_price, exit_reason)
                    stock_trades.append(active_trade)
                    active_trade = None
                    print_success(f"Exit at {current_time.strftime('%H:%M:%S')} @ ₹{exit_price:.2f} - {exit_reason}")
                    continue

            # Check for new entry signals (max 2 entries)
            if active_trade is None and entry_count < self.max_entries_per_stock:

                # Long signal: Close above setup high
                if current_close > setup_high:
                    quantity = self.calculate_position_size(current_close)
                    stop_loss = setup_low
                    target = self.calculate_target_price(current_close, stop_loss, 'LONG') \
                             if self.exit_strategy.use_rr else None

                    active_trade = Trade(
                        symbol=symbol,
                        direction='LONG',
                        entry_time=current_time,
                        entry_price=current_close,
                        quantity=quantity,
                        stop_loss=stop_loss,
                        target_price=target
                    )
                    entry_count += 1
                    print_success(f"LONG Entry #{entry_count} at {current_time.strftime('%H:%M:%S')} @ ₹{current_close:.2f}")
                    if target:
                        print_info(f"  Target: ₹{target:.2f} | Stop Loss: ₹{stop_loss:.2f}")

                # Short signal: Close below setup low
                elif current_close < setup_low:
                    quantity = self.calculate_position_size(current_close)
                    stop_loss = setup_high
                    target = self.calculate_target_price(current_close, stop_loss, 'SHORT') \
                             if self.exit_strategy.use_rr else None

                    active_trade = Trade(
                        symbol=symbol,
                        direction='SHORT',
                        entry_time=current_time,
                        entry_price=current_close,
                        quantity=quantity,
                        stop_loss=stop_loss,
                        target_price=target
                    )
                    entry_count += 1
                    print_success(f"SHORT Entry #{entry_count} at {current_time.strftime('%H:%M:%S')} @ ₹{current_close:.2f}")
                    if target:
                        print_info(f"  Target: ₹{target:.2f} | Stop Loss: ₹{stop_loss:.2f}")

        # Close any remaining open trade at end of data
        if active_trade:
            last_row = df_reset.iloc[-1]
            active_trade.close_trade(last_row['datetime'], last_row['close'], 'EOD_EXIT')
            stock_trades.append(active_trade)

        return stock_trades

    def generate_report(self, all_trades: List[Trade], stocks: List[str]):
        """Generate comprehensive backtest report with table formatting"""
        print_header("BACKTEST REPORT - Enhanced First Red Candle Strategy")

        # Overall Statistics
        total_trades = len(all_trades)
        if total_trades == 0:
            print_warning("\nNo trades executed!")
            return

        winning_trades = [t for t in all_trades if t.pnl > 0]
        losing_trades = [t for t in all_trades if t.pnl < 0]
        breakeven_trades = [t for t in all_trades if t.pnl == 0]

        total_profit = sum(t.pnl for t in winning_trades)
        total_loss = sum(t.pnl for t in losing_trades)
        net_pnl = sum(t.pnl for t in all_trades)

        win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0

        # Calculate ROI
        roi = (net_pnl / self.initial_capital) * 100

        # Calculate drawdown
        cumulative_pnl = []
        running_pnl = 0
        for trade in all_trades:
            running_pnl += trade.pnl
            cumulative_pnl.append(running_pnl)

        peak = cumulative_pnl[0] if cumulative_pnl else 0
        max_drawdown = 0
        for pnl in cumulative_pnl:
            if pnl > peak:
                peak = pnl
            drawdown = peak - pnl
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        max_drawdown_percent = (max_drawdown / self.initial_capital) * 100

        avg_win = total_profit / len(winning_trades) if len(winning_trades) > 0 else 0
        avg_loss = abs(total_loss / len(losing_trades)) if len(losing_trades) > 0 else 0
        risk_reward = avg_win / avg_loss if avg_loss > 0 else 0

        # ═══════════════════════════════════════════════════════════════
        # EXIT STRATEGY CONFIGURATION
        # ═══════════════════════════════════════════════════════════════
        print(f"\n{Colors.BOLD}╔{'═' * 78}╗{Colors.ENDC}")
        print(f"{Colors.BOLD}║{'EXIT STRATEGY CONFIGURATION'.center(78)}║{Colors.ENDC}")
        print(f"{Colors.BOLD}╚{'═' * 78}╝{Colors.ENDC}\n")

        exit_config = []
        if self.exit_strategy.use_rr:
            exit_config.append(["Risk-Reward Exit", f"✓ Enabled (RR: 1:{self.exit_strategy.rr_ratio})"])
        if self.exit_strategy.use_atr:
            exit_config.append(["ATR-Based Exit", f"✓ Enabled ({self.exit_strategy.atr_multiplier}x ATR)"])
        if self.exit_strategy.use_trailing_sl:
            exit_config.append(["Trailing Stop Loss", f"✓ Enabled ({self.exit_strategy.trailing_sl_percent}%)"])
        if self.exit_strategy.use_ema_exit:
            exit_config.append(["EMA Crossover Exit", f"✓ Enabled (EMA {self.exit_strategy.ema_period})"])
        if self.exit_strategy.use_time_exit:
            exit_config.append(["Time-Based Exit", f"✓ Enabled ({self.exit_strategy.exit_time})"])

        print(tabulate(exit_config, headers=["Exit Strategy", "Status"], tablefmt="grid"))

        # ═══════════════════════════════════════════════════════════════
        # CAPITAL CONFIGURATION TABLE
        # ═══════════════════════════════════════════════════════════════
        print(f"\n{Colors.BOLD}╔{'═' * 78}╗{Colors.ENDC}")
        print(f"{Colors.BOLD}║{'CAPITAL CONFIGURATION'.center(78)}║{Colors.ENDC}")
        print(f"{Colors.BOLD}╚{'═' * 78}╝{Colors.ENDC}\n")

        capital_data = [
            ["Initial Capital", f"₹{self.initial_capital:,.2f}"],
            ["Leverage", f"{self.leverage}x"],
            ["Buying Power", f"₹{self.buying_power:,.2f}"],
            ["Final Capital", f"₹{self.initial_capital + net_pnl:,.2f}"]
        ]
        print(tabulate(capital_data, headers=["Parameter", "Value"], tablefmt="grid"))

        # ═══════════════════════════════════════════════════════════════
        # PERFORMANCE SUMMARY TABLE
        # ═══════════════════════════════════════════════════════════════
        print(f"\n{Colors.BOLD}╔{'═' * 78}╗{Colors.ENDC}")
        print(f"{Colors.BOLD}║{'PERFORMANCE SUMMARY'.center(78)}║{Colors.ENDC}")
        print(f"{Colors.BOLD}╚{'═' * 78}╝{Colors.ENDC}\n")

        performance_data = [
            ["Total Trades", total_trades],
            ["Winning Trades", f"{len(winning_trades)} ({win_rate:.2f}%)"],
            ["Losing Trades", f"{len(losing_trades)} ({len(losing_trades)/total_trades*100:.2f}%)"],
            ["Breakeven Trades", len(breakeven_trades)],
            ["Win Rate", f"{win_rate:.2f}%"]
        ]
        print(tabulate(performance_data, headers=["Metric", "Value"], tablefmt="grid"))

        # ═══════════════════════════════════════════════════════════════
        # PROFIT & LOSS TABLE
        # ═══════════════════════════════════════════════════════════════
        print(f"\n{Colors.BOLD}╔{'═' * 78}╗{Colors.ENDC}")
        print(f"{Colors.BOLD}║{'PROFIT & LOSS'.center(78)}║{Colors.ENDC}")
        print(f"{Colors.BOLD}╚{'═' * 78}╝{Colors.ENDC}\n")

        pnl_data = [
            ["Total Profit", f"₹{total_profit:,.2f}"],
            ["Total Loss", f"₹{total_loss:,.2f}"],
            ["Net P&L", f"₹{net_pnl:,.2f}"],
            ["ROI", f"{roi:.2f}%"],
            ["Average Win", f"₹{avg_win:,.2f}"],
            ["Average Loss", f"₹{avg_loss:,.2f}"]
        ]
        print(tabulate(pnl_data, headers=["Metric", "Value"], tablefmt="grid"))

        # ═══════════════════════════════════════════════════════════════
        # RISK METRICS TABLE
        # ═══════════════════════════════════════════════════════════════
        print(f"\n{Colors.BOLD}╔{'═' * 78}╗{Colors.ENDC}")
        print(f"{Colors.BOLD}║{'RISK METRICS'.center(78)}║{Colors.ENDC}")
        print(f"{Colors.BOLD}╚{'═' * 78}╝{Colors.ENDC}\n")

        risk_data = [
            ["Max Drawdown", f"₹{max_drawdown:,.2f} ({max_drawdown_percent:.2f}%)"],
            ["Risk-Reward Ratio", f"{risk_reward:.2f}" if risk_reward > 0 else "N/A"],
            ["Expectancy", f"₹{net_pnl/total_trades:.2f} per trade"]
        ]
        print(tabulate(risk_data, headers=["Metric", "Value"], tablefmt="grid"))

        # ═══════════════════════════════════════════════════════════════
        # EXIT REASON BREAKDOWN
        # ═══════════════════════════════════════════════════════════════
        print(f"\n{Colors.BOLD}╔{'═' * 78}╗{Colors.ENDC}")
        print(f"{Colors.BOLD}║{'EXIT REASON BREAKDOWN'.center(78)}║{Colors.ENDC}")
        print(f"{Colors.BOLD}╚{'═' * 78}╝{Colors.ENDC}\n")

        exit_reasons = defaultdict(int)
        exit_pnl = defaultdict(float)
        for trade in all_trades:
            exit_reasons[trade.exit_reason] += 1
            exit_pnl[trade.exit_reason] += trade.pnl

        exit_breakdown = []
        for reason, count in exit_reasons.items():
            pnl = exit_pnl[reason]
            exit_breakdown.append([
                reason,
                count,
                f"{(count/total_trades)*100:.1f}%",
                f"₹{pnl:,.2f}"
            ])

        print(tabulate(exit_breakdown, 
                      headers=["Exit Reason", "Count", "% of Total", "Total P&L"], 
                      tablefmt="grid"))

        # ═══════════════════════════════════════════════════════════════
        # PER-STOCK PERFORMANCE TABLE
        # ═══════════════════════════════════════════════════════════════
        print(f"\n{Colors.BOLD}╔{'═' * 78}╗{Colors.ENDC}")
        print(f"{Colors.BOLD}║{'PER-STOCK PERFORMANCE'.center(78)}║{Colors.ENDC}")
        print(f"{Colors.BOLD}╚{'═' * 78}╝{Colors.ENDC}\n")

        stock_performance = defaultdict(lambda: {'trades': [], 'pnl': 0})

        for trade in all_trades:
            stock_performance[trade.symbol]['trades'].append(trade)
            stock_performance[trade.symbol]['pnl'] += trade.pnl

        stock_table_data = []
        for symbol in stocks:
            if symbol in stock_performance:
                trades = stock_performance[symbol]['trades']
                pnl = stock_performance[symbol]['pnl']
                wins = len([t for t in trades if t.pnl > 0])
                losses = len([t for t in trades if t.pnl < 0])
                win_rate_stock = (wins / len(trades) * 100) if len(trades) > 0 else 0

                stock_table_data.append([
                    symbol,
                    len(trades),
                    f"{wins}/{len(trades)}",
                    f"{win_rate_stock:.1f}%",
                    f"₹{pnl:,.2f}"
                ])
            else:
                stock_table_data.append([
                    symbol,
                    0,
                    "0/0",
                    "0.0%",
                    "No trades"
                ])

        print(tabulate(stock_table_data, 
                      headers=["Stock", "Trades", "Wins", "Win Rate", "P&L"], 
                      tablefmt="grid"))

        # ═══════════════════════════════════════════════════════════════
        # DETAILED TRADE LOG TABLE
        # ═══════════════════════════════════════════════════════════════
        print(f"\n{Colors.BOLD}╔{'═' * 78}╗{Colors.ENDC}")
        print(f"{Colors.BOLD}║{'DETAILED TRADE LOG'.center(78)}║{Colors.ENDC}")
        print(f"{Colors.BOLD}╚{'═' * 78}╝{Colors.ENDC}\n")

        trade_table_data = []
        for i, trade in enumerate(all_trades, 1):
            status = "PROFIT" if trade.pnl > 0 else ("LOSS" if trade.pnl < 0 else "B/E")

            trade_table_data.append([
                i,
                trade.symbol,
                trade.direction,
                trade.entry_time.strftime('%H:%M:%S'),
                f"₹{trade.entry_price:.2f}",
                trade.quantity,
                f"₹{trade.initial_stop_loss:.2f}",
                trade.exit_time.strftime('%H:%M:%S') if trade.exit_time else '-',
                f"₹{trade.exit_price:.2f}" if trade.exit_price else '-',
                trade.exit_reason[:12] if trade.exit_reason else '-',
                f"₹{trade.pnl:.2f}",
                f"{trade.pnl_percent:.2f}%",
                status
            ])

        print(tabulate(trade_table_data,
                      headers=["#", "Stock", "Dir", "Entry", "Entry₹", "Qty", 
                              "StopLoss", "Exit", "Exit₹", "Reason", 
                              "P&L", "P&L%", "Result"],
                      tablefmt="grid"))


def get_stock_input() -> List[str]:
    """Get stock symbols from user"""
    print_header("Stock Selection")
    print("Enter stock symbols (comma-separated)")
    print("Example: RELIANCE, TCS, INFY, HDFCBANK")
    print("Note: Use NSE trading symbols\n")

    stocks_input = input(f"{Colors.BOLD}Enter stock symbols: {Colors.ENDC}").strip()
    stocks = [s.strip().upper() for s in stocks_input.split(',')]

    return stocks


def get_date_input() -> datetime:
    """Get backtest date from user"""
    print_header("Date Selection")
    print("1. Press Enter for today's date")
    print("2. Enter custom date (YYYY-MM-DD format)")

    date_input = input(f"\n{Colors.BOLD}Enter date or press Enter for today: {Colors.ENDC}").strip()

    if not date_input:
        return datetime.now()

    try:
        return datetime.strptime(date_input, '%Y-%m-%d')
    except ValueError:
        print_error("Invalid date format! Using today's date.")
        return datetime.now()


def get_exit_strategy_config() -> ExitStrategy:
    """Get exit strategy configuration from user"""
    print_header("Exit Strategy Configuration")
    print("Select exit strategies to enable:\n")

    # Risk-Reward Exit
    print(f"{Colors.BOLD}1. Risk-Reward (RR) Target Exit{Colors.ENDC}")
    use_rr = input("Enable RR exit? (y/n): ").strip().lower() == 'y'
    rr_ratio = 2.0
    if use_rr:
        try:
            rr_input = input("Enter RR ratio (default 2.0): ").strip()
            rr_ratio = float(rr_input) if rr_input else 2.0
        except:
            rr_ratio = 2.0

    # ATR-based Exit
    print(f"\n{Colors.BOLD}2. ATR-Based Exit{Colors.ENDC}")
    use_atr = input("Enable ATR exit? (y/n): ").strip().lower() == 'y'
    atr_multiplier = 2.0
    if use_atr:
        try:
            atr_input = input("Enter ATR multiplier (default 2.0): ").strip()
            atr_multiplier = float(atr_input) if atr_input else 2.0
        except:
            atr_multiplier = 2.0

    # Trailing Stop Loss
    print(f"\n{Colors.BOLD}3. Trailing Stop Loss{Colors.ENDC}")
    use_trailing = input("Enable trailing stop loss? (y/n): ").strip().lower() == 'y'
    trailing_percent = 1.0
    if use_trailing:
        try:
            trailing_input = input("Enter trailing % (default 1.0): ").strip()
            trailing_percent = float(trailing_input) if trailing_input else 1.0
        except:
            trailing_percent = 1.0

    # EMA Exit
    print(f"\n{Colors.BOLD}4. EMA Crossover Exit{Colors.ENDC}")
    use_ema = input("Enable EMA exit? (y/n): ").strip().lower() == 'y'
    ema_period = 10
    if use_ema:
        try:
            ema_input = input("Enter EMA period (default 10): ").strip()
            ema_period = int(ema_input) if ema_input else 10
        except:
            ema_period = 10

    # Time Exit
    print(f"\n{Colors.BOLD}5. Time-Based Exit{Colors.ENDC}")
    use_time = input("Enable time exit? (y/n, default y): ").strip().lower() != 'n'
    exit_time = "14:55"
    if use_time:
        time_input = input("Enter exit time HH:MM (default 14:55): ").strip()
        exit_time = time_input if time_input else "14:55"

    return ExitStrategy(
        use_rr=use_rr,
        rr_ratio=rr_ratio,
        use_atr=use_atr,
        atr_multiplier=atr_multiplier,
        use_trailing_sl=use_trailing,
        trailing_sl_percent=trailing_percent,
        use_ema_exit=use_ema,
        ema_period=ema_period,
        use_time_exit=use_time,
        exit_time=exit_time
    )


def main():
    """Main execution function"""
    print_header("Enhanced First Red Candle Breakout Strategy - Backtester")

    # Check authentication
    api_key = os.getenv('ZERODHA_API_KEY')
    access_token = os.getenv('ZERODHA_ACCESS_TOKEN')

    if not api_key or not access_token:
        print_error("Zerodha credentials not found!")
        print_info("Please run auth_helper.py first to authenticate")
        sys.exit(1)

    # Initialize Kite Connect
    try:
        kite = KiteConnect(api_key=api_key)
        kite.set_access_token(access_token)

        # Verify connection
        profile = kite.profile()
        print_success(f"Authenticated as: {profile['user_name']} ({profile['user_id']})")
    except Exception as e:
        print_error(f"Authentication failed: {e}")
        print_info("Please run auth_helper.py to refresh your access token")
        sys.exit(1)

    # Get user inputs
    stocks = get_stock_input()
    backtest_date = get_date_input()
    exit_strategy = get_exit_strategy_config()

    print_info(f"\nBacktesting {len(stocks)} stocks for {backtest_date.strftime('%Y-%m-%d')}")

    # Initialize backtester
    backtester = StrategyBacktester(kite, capital=10000, leverage=5.0, 
                                   exit_strategy=exit_strategy)

    # Run backtest for each stock
    all_trades = []

    for stock in stocks:
        try:
            trades = backtester.backtest_stock(stock, backtest_date)
            all_trades.extend(trades)
            print_success(f"Completed {stock}: {len(trades)} trades\n")
        except Exception as e:
            print_error(f"Error backtesting {stock}: {e}\n")
            continue

    # Generate comprehensive report
    if all_trades:
        backtester.generate_report(all_trades, stocks)
    else:
        print_warning("No trades were executed. Possible reasons:")
        print("  - Market was closed on selected date")
        print("  - No trading data available")
        print("  - No first red candle found")
        print("  - No breakout signals generated")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.WARNING}Backtest cancelled by user{Colors.ENDC}")
    except Exception as e:
        print_error(f"An unexpected error occurred: {e}")
        import traceback
        traceback.print_exc()