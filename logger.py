#!/usr/bin/env python3
"""
Production Trading Bot - Logging System
=======================================
Comprehensive logging for trading operations, errors, and monitoring
"""

import logging
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional
import traceback

# ANSI color codes for console output
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


class ColoredFormatter(logging.Formatter):
    """Custom formatter with colors for console output"""

    COLORS = {
        'DEBUG': Colors.OKBLUE,
        'INFO': Colors.OKCYAN,
        'WARNING': Colors.WARNING,
        'ERROR': Colors.FAIL,
        'CRITICAL': Colors.FAIL + Colors.BOLD
    }

    def format(self, record):
        # Add color to level name
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{Colors.ENDC}"

        return super().format(record)


class TradingLogger:
    """Centralized logging system for trading bot"""

    def __init__(self, 
                 name: str = 'TradingBot',
                 log_file: Optional[str] = None,
                 log_level: str = 'INFO',
                 enable_console: bool = True,
                 enable_file: bool = True):

        self.logger = logging.getLogger(name)
        self.logger.setLevel(getattr(logging, log_level.upper()))
        self.logger.handlers.clear()  # Clear existing handlers

        # Create formatters
        file_formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )

        console_formatter = ColoredFormatter(
            '%(asctime)s | %(levelname)-8s | %(message)s',
            datefmt='%H:%M:%S'
        )

        # Console handler
        if enable_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.DEBUG)
            console_handler.setFormatter(console_formatter)
            self.logger.addHandler(console_handler)

        # File handler
        if enable_file and log_file:
            # Create logs directory if it doesn't exist
            log_path = Path(log_file)
            log_path.parent.mkdir(parents=True, exist_ok=True)

            # Create file handler
            file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            file_handler.setFormatter(file_formatter)
            self.logger.addHandler(file_handler)

            # Create separate error log
            error_log = log_path.parent / f"{log_path.stem}_errors.log"
            error_handler = logging.FileHandler(error_log, mode='a', encoding='utf-8')
            error_handler.setLevel(logging.ERROR)
            error_handler.setFormatter(file_formatter)
            self.logger.addHandler(error_handler)

    def debug(self, message: str, **kwargs):
        """Log debug message"""
        self.logger.debug(message, **kwargs)

    def info(self, message: str, **kwargs):
        """Log info message"""
        self.logger.info(message, **kwargs)

    def warning(self, message: str, **kwargs):
        """Log warning message"""
        self.logger.warning(message, **kwargs)

    def error(self, message: str, exc_info: bool = False, **kwargs):
        """Log error message"""
        self.logger.error(message, exc_info=exc_info, **kwargs)

    def critical(self, message: str, exc_info: bool = True, **kwargs):
        """Log critical message"""
        self.logger.critical(message, exc_info=exc_info, **kwargs)

    def trade_entry(self, symbol: str, direction: str, quantity: int, 
                    price: float, stop_loss: float, target: float = None):
        """Log trade entry"""
        msg = (f"🔵 ENTRY | {symbol} | {direction} | "
               f"Qty: {quantity} | Entry: ₹{price:.2f} | "
               f"SL: ₹{stop_loss:.2f}")
        if target:
            msg += f" | Target: ₹{target:.2f}"
        self.logger.info(msg)

    def trade_exit(self, symbol: str, direction: str, quantity: int,
                   entry_price: float, exit_price: float, 
                   pnl: float, reason: str):
        """Log trade exit"""
        pnl_symbol = "🟢" if pnl > 0 else "🔴" if pnl < 0 else "⚪"
        msg = (f"{pnl_symbol} EXIT | {symbol} | {direction} | "
               f"Qty: {quantity} | Entry: ₹{entry_price:.2f} | "
               f"Exit: ₹{exit_price:.2f} | P&L: ₹{pnl:.2f} | "
               f"Reason: {reason}")

        if pnl > 0:
            self.logger.info(msg)
        elif pnl < 0:
            self.logger.warning(msg)
        else:
            self.logger.info(msg)

    def trade_update(self, symbol: str, update: str):
        """Log trade update"""
        self.logger.info(f"📊 UPDATE | {symbol} | {update}")

    def order_placed(self, order_id: str, symbol: str, transaction_type: str,
                     quantity: int, price: float = None):
        """Log order placement"""
        price_str = f"@ ₹{price:.2f}" if price else "@ Market"
        self.logger.info(f"📤 ORDER | ID: {order_id} | {symbol} | "
                        f"{transaction_type} {quantity} {price_str}")

    def order_failed(self, symbol: str, reason: str):
        """Log order failure"""
        self.logger.error(f"❌ ORDER FAILED | {symbol} | {reason}")

    def system_start(self, capital: float, leverage: float):
        """Log system start"""
        buying_power = capital * leverage
        self.logger.info("=" * 80)
        self.logger.info(f"🚀 TRADING BOT STARTED")
        self.logger.info(f"Capital: ₹{capital:,.0f} | Leverage: {leverage}x | "
                        f"Buying Power: ₹{buying_power:,.0f}")
        self.logger.info("=" * 80)

    def system_stop(self, reason: str = "Normal shutdown"):
        """Log system stop"""
        self.logger.info("=" * 80)
        self.logger.info(f"🛑 TRADING BOT STOPPED | Reason: {reason}")
        self.logger.info("=" * 80)

    def daily_summary(self, trades: int, wins: int, losses: int, 
                     total_pnl: float, win_rate: float):
        """Log daily summary"""
        self.logger.info("=" * 80)
        self.logger.info("📈 DAILY SUMMARY")
        self.logger.info(f"Trades: {trades} | Wins: {wins} | Losses: {losses} | "
                        f"Win Rate: {win_rate:.1f}%")
        self.logger.info(f"Total P&L: ₹{total_pnl:,.2f}")
        self.logger.info("=" * 80)

    def circuit_breaker_triggered(self, reason: str, current_loss: float):
        """Log circuit breaker trigger"""
        self.logger.critical(f"⚠️  CIRCUIT BREAKER TRIGGERED!")
        self.logger.critical(f"Reason: {reason}")
        self.logger.critical(f"Current Loss: ₹{current_loss:,.2f}")
        self.logger.critical("All positions will be closed and trading stopped")

    def api_error(self, endpoint: str, error: Exception):
        """Log API error"""
        self.logger.error(f"🔌 API ERROR | Endpoint: {endpoint} | "
                         f"Error: {str(error)}", exc_info=True)

    def network_error(self, error: str):
        """Log network error"""
        self.logger.error(f"🌐 NETWORK ERROR | {error}")

    def exception(self, context: str, exception: Exception):
        """Log exception with full traceback"""
        self.logger.error(f"💥 EXCEPTION in {context}: {str(exception)}")
        self.logger.error(traceback.format_exc())


def print_header(text: str):
    """Print colored header"""
    print(f"\n{Colors.HEADER}{Colors.BOLD}{'=' * 80}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{text.center(80)}{Colors.ENDC}")
    print(f"{Colors.HEADER}{Colors.BOLD}{'=' * 80}{Colors.ENDC}\n")


def print_success(text: str):
    """Print success message"""
    print(f"{Colors.OKGREEN}✓ {text}{Colors.ENDC}")


def print_error(text: str):
    """Print error message"""
    print(f"{Colors.FAIL}✗ {text}{Colors.ENDC}")


def print_warning(text: str):
    """Print warning message"""
    print(f"{Colors.WARNING}⚠ {text}{Colors.ENDC}")


def print_info(text: str):
    """Print info message"""
    print(f"{Colors.OKCYAN}ℹ {text}{Colors.ENDC}")


# Singleton logger instance
_logger_instance: Optional[TradingLogger] = None


def get_logger(name: str = 'TradingBot', 
               log_file: str = 'logs/trading_bot.log',
               log_level: str = 'INFO',
               enable_console: bool = True,
               enable_file: bool = True) -> TradingLogger:
    """Get or create logger instance"""
    global _logger_instance

    if _logger_instance is None:
        _logger_instance = TradingLogger(
            name=name,
            log_file=log_file,
            log_level=log_level,
            enable_console=enable_console,
            enable_file=enable_file
        )

    return _logger_instance