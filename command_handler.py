#!/usr/bin/env python3
"""
Production Trading Bot - Command Handler
========================================
Runtime commands to control the bot without stopping it
"""

import threading
from typing import Set, Callable
from logger import Colors


class CommandHandler:
    """Handle runtime commands for bot control"""

    def __init__(self, logger):
        self.logger = logger
        self.stopped_stocks: Set[str] = set()
        self.running = True
        self.command_thread = None

        # Command callbacks
        self.callbacks = {
            'on_stop_stock': None,
            'on_resume_stock': None,
            'on_add_stock': None,
            'on_status': None,
            'on_shutdown': None,
            'on_emergency_stop': None,
            'on_exit_position': None
        }

    def register_callback(self, event: str, callback: Callable):
        """Register callback for command events"""
        if event in self.callbacks:
            self.callbacks[event] = callback

    def start_command_listener(self):
        """Start background thread to listen for commands"""
        self.command_thread = threading.Thread(target=self._listen_for_commands, daemon=True)
        self.command_thread.start()

        print(f"\n{Colors.OKCYAN}{'=' * 80}{Colors.ENDC}")
        print(f"{Colors.BOLD}{Colors.OKCYAN}📟 COMMAND INTERFACE ACTIVE{Colors.ENDC}")
        print(f"{Colors.OKCYAN}{'=' * 80}{Colors.ENDC}")
        print(f"{Colors.OKBLUE}Available Commands:{Colors.ENDC}")
        print(f"  {Colors.BOLD}add <SYMBOL>{Colors.ENDC}      - Add a new stock to monitor (e.g., add INFY)")
        print(f"  {Colors.BOLD}stop <SYMBOL>{Colors.ENDC}     - Stop monitoring a stock (e.g., stop RELIANCE)")
        print(f"  {Colors.BOLD}resume <SYMBOL>{Colors.ENDC}   - Resume monitoring a stock (e.g., resume RELIANCE)")
        print(f"  {Colors.BOLD}stop all{Colors.ENDC}          - Stop monitoring all stocks")
        print(f"  {Colors.BOLD}resume all{Colors.ENDC}        - Resume monitoring all stocks")
        print(f"  {Colors.BOLD}list{Colors.ENDC}              - Show stopped stocks")
        print(f"  {Colors.BOLD}status{Colors.ENDC}            - Show bot status")
        print(f"  {Colors.BOLD}exit <SYMBOL>{Colors.ENDC}     - Exit position for specific stock (e.g., exit LTF)")
        print(f"  {Colors.BOLD}exit{Colors.ENDC}              - Shutdown bot gracefully")
        print(f"  {Colors.BOLD}emergency{Colors.ENDC}         - EMERGENCY STOP: Exit all positions & halt trading")
        print(f"  {Colors.BOLD}help{Colors.ENDC}              - Show this help")
        print(f"{Colors.OKCYAN}{'=' * 80}{Colors.ENDC}\n")

    def _listen_for_commands(self):
        """Background thread to listen for user commands"""
        while self.running:
            try:
                # Non-blocking input with timeout
                command = input(f"{Colors.BOLD}Command > {Colors.ENDC}").strip().lower()

                if not command:
                    continue

                self._process_command(command)

            except EOFError:
                # Input closed, stop listening
                break
            except KeyboardInterrupt:
                # Handle Ctrl+C gracefully
                break
            except Exception as e:
                self.logger.error(f"Command handler error: {str(e)}")

    def _process_command(self, command: str):
        """Process user command"""
        parts = command.split()

        if not parts:
            return

        cmd = parts[0]

        # ADD command
        if cmd == 'add':
            if len(parts) < 2:
                print(f"{Colors.WARNING}Usage: add <SYMBOL>{Colors.ENDC}")
                return

            symbol = parts[1].upper()
            self._add_stock(symbol)

        # STOP command
        elif cmd == 'stop':
            if len(parts) < 2:
                print(f"{Colors.WARNING}Usage: stop <SYMBOL> or stop all{Colors.ENDC}")
                return

            if parts[1] == 'all':
                self._stop_all_stocks()
            else:
                symbol = parts[1].upper()
                self._stop_stock(symbol)

        # RESUME command
        elif cmd == 'resume':
            if len(parts) < 2:
                print(f"{Colors.WARNING}Usage: resume <SYMBOL> or resume all{Colors.ENDC}")
                return

            if parts[1] == 'all':
                self._resume_all_stocks()
            else:
                symbol = parts[1].upper()
                self._resume_stock(symbol)

        # LIST command
        elif cmd == 'list':
            self._list_stopped_stocks()

        # STATUS command
        elif cmd == 'status':
            if self.callbacks['on_status']:
                self.callbacks['on_status']()

        # EMERGENCY STOP command
        elif cmd == 'emergency':
            self._emergency_stop()

        # HELP command
        elif cmd == 'help':
            self._show_help()

        # EXIT command
        elif cmd in ['exit', 'quit', 'shutdown']:
            # Check if stock symbol provided for position exit
            if len(parts) >= 2:
                symbol = parts[1].upper()
                self._exit_position(symbol)
            else:
                # No symbol - shutdown bot
                self._shutdown()

        else:
            print(f"{Colors.FAIL}Unknown command: {cmd}{Colors.ENDC}")
            print(f"Type {Colors.BOLD}'help'{Colors.ENDC} for available commands")

    def _add_stock(self, symbol: str):
        """Add a new stock to monitor"""
        print(f"{Colors.OKGREEN}➕ Adding stock: {symbol}{Colors.ENDC}")
        self.logger.info(f"Adding stock {symbol} via command")

        # Trigger callback
        if self.callbacks['on_add_stock']:
            self.callbacks['on_add_stock'](symbol)

    def _stop_stock(self, symbol: str):
        """Stop monitoring a specific stock"""
        if symbol in self.stopped_stocks:
            print(f"{Colors.WARNING}⚠ {symbol} is already stopped{Colors.ENDC}")
            return

        self.stopped_stocks.add(symbol)
        print(f"{Colors.FAIL}🛑 Stopped monitoring: {symbol}{Colors.ENDC}")
        self.logger.warning(f"Stopped monitoring {symbol} via command")

        # Trigger callback
        if self.callbacks['on_stop_stock']:
            self.callbacks['on_stop_stock'](symbol)

    def _resume_stock(self, symbol: str):
        """Resume monitoring a specific stock"""
        if symbol not in self.stopped_stocks:
            print(f"{Colors.WARNING}⚠ {symbol} is not stopped{Colors.ENDC}")
            return

        self.stopped_stocks.remove(symbol)
        print(f"{Colors.OKGREEN}✓ Resumed monitoring: {symbol}{Colors.ENDC}")
        self.logger.info(f"Resumed monitoring {symbol} via command")

        # Trigger callback
        if self.callbacks['on_resume_stock']:
            self.callbacks['on_resume_stock'](symbol)

    def _stop_all_stocks(self):
        """Stop monitoring all stocks"""
        if not self.stopped_stocks:
            # Get all stocks from callback
            print(f"{Colors.FAIL}🛑 Stopping all stocks...{Colors.ENDC}")

        # Callback will handle getting stock list
        if self.callbacks['on_stop_stock']:
            self.callbacks['on_stop_stock']('ALL')

        self.logger.warning("Stopped monitoring ALL stocks via command")

    def _resume_all_stocks(self):
        """Resume monitoring all stocks"""
        if not self.stopped_stocks:
            print(f"{Colors.WARNING}⚠ No stocks are currently stopped{Colors.ENDC}")
            return

        count = len(self.stopped_stocks)
        self.stopped_stocks.clear()
        print(f"{Colors.OKGREEN}✓ Resumed monitoring all {count} stocks{Colors.ENDC}")
        self.logger.info("Resumed monitoring ALL stocks via command")

        # Trigger callback
        if self.callbacks['on_resume_stock']:
            self.callbacks['on_resume_stock']('ALL')

    def _list_stopped_stocks(self):
        """List all stopped stocks"""
        if not self.stopped_stocks:
            print(f"{Colors.OKGREEN}✓ No stocks are currently stopped{Colors.ENDC}")
        else:
            print(f"\n{Colors.WARNING}🛑 Stopped Stocks ({len(self.stopped_stocks)}):{Colors.ENDC}")
            for symbol in sorted(self.stopped_stocks):
                print(f"  • {symbol}")
            print()

    def _show_help(self):
        """Show help message"""
        print(f"\n{Colors.BOLD}Available Commands:{Colors.ENDC}")
        print(f"  {Colors.BOLD}add <SYMBOL>{Colors.ENDC}      - Add a new stock to monitor")
        print(f"                      Example: add INFY")
        print(f"  {Colors.BOLD}stop <SYMBOL>{Colors.ENDC}     - Stop monitoring a stock")
        print(f"                      Example: stop RELIANCE")
        print(f"  {Colors.BOLD}resume <SYMBOL>{Colors.ENDC}   - Resume monitoring a stock")
        print(f"                      Example: resume RELIANCE")
        print(f"  {Colors.BOLD}stop all{Colors.ENDC}          - Stop monitoring all stocks")
        print(f"  {Colors.BOLD}resume all{Colors.ENDC}        - Resume monitoring all stocks")
        print(f"  {Colors.BOLD}list{Colors.ENDC}              - Show stopped stocks")
        print(f"  {Colors.BOLD}status{Colors.ENDC}            - Show current bot status")
        print(f"  {Colors.BOLD}exit <SYMBOL>{Colors.ENDC}     - Exit position for a specific stock")
        print(f"                      Example: exit LTF")
        print(f"  {Colors.BOLD}exit{Colors.ENDC}              - Shutdown bot gracefully")
        print(f"  {Colors.BOLD}emergency{Colors.ENDC}         - EMERGENCY STOP: Exit all positions & halt trading")
        print(f"  {Colors.BOLD}help{Colors.ENDC}              - Show this help message")
        print()

    def _emergency_stop(self):
        """Emergency stop - exit all positions and halt trading"""
        print(f"\n{Colors.FAIL}{'=' * 80}{Colors.ENDC}")
        print(f"{Colors.FAIL}🚨 EMERGENCY STOP ACTIVATED 🚨{Colors.ENDC}")
        print(f"{Colors.FAIL}{'=' * 80}{Colors.ENDC}")
        print(f"{Colors.WARNING}Exiting all positions and halting all trading...{Colors.ENDC}\n")

        self.logger.critical("EMERGENCY STOP activated via command")

        if self.callbacks['on_emergency_stop']:
            self.callbacks['on_emergency_stop']()

    def _exit_position(self, symbol: str):
        """Exit position for a specific stock"""
        print(f"\n{Colors.WARNING}⚠ Exiting position for {symbol}...{Colors.ENDC}")
        self.logger.info(f"Exit position command for {symbol}")

        if self.callbacks['on_exit_position']:
            self.callbacks['on_exit_position'](symbol)

    def _shutdown(self):
        """Shutdown the bot"""
        print(f"\n{Colors.WARNING}⚠ Initiating graceful shutdown...{Colors.ENDC}")
        self.logger.warning("Shutdown initiated via command")

        if self.callbacks['on_shutdown']:
            self.callbacks['on_shutdown']()

        self.running = False

    def is_stock_stopped(self, symbol: str) -> bool:
        """Check if a stock is stopped"""
        return symbol in self.stopped_stocks

    def stop(self):
        """Stop command handler"""
        self.running = False