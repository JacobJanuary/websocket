#!/usr/bin/env python3
"""
Monitoring dashboard for Signal WebSocket Server
Provides real-time metrics and health checks
"""

import asyncio
import json
import sys
import os
from datetime import datetime, timedelta
from typing import Optional
import curses
from signal_websocket_client import SignalWebSocketClient


class SignalMonitor:
    """Real-time monitoring dashboard for Signal WebSocket"""

    def __init__(self, config: dict):
        self.config = config
        self.client = SignalWebSocketClient(config)
        self.running = False

        # Metrics
        self.metrics = {
            'connection_state': 'disconnected',
            'signals_total': 0,
            'signals_per_minute': [],
            'last_signal_time': None,
            'server_stats': {},
            'recent_signals': [],
            'errors': []
        }

        # Setup callbacks
        self.client.set_callbacks(
            on_signals=self.on_signals,
            on_connect=self.on_connect,
            on_disconnect=self.on_disconnect,
            on_error=self.on_error
        )

    async def on_signals(self, signals):
        """Process received signals"""
        self.metrics['signals_total'] += len(signals)
        self.metrics['last_signal_time'] = datetime.now()

        # Track signals per minute
        now = datetime.now()
        self.metrics['signals_per_minute'].append({
            'time': now,
            'count': len(signals)
        })

        # Keep only last 60 minutes
        cutoff = now - timedelta(minutes=60)
        self.metrics['signals_per_minute'] = [
            s for s in self.metrics['signals_per_minute']
            if s['time'] > cutoff
        ]

        # Store recent signals
        self.metrics['recent_signals'] = (signals[:10] + self.metrics['recent_signals'])[:50]

    async def on_connect(self):
        """Handle connection event"""
        self.metrics['connection_state'] = 'connected'

    async def on_disconnect(self):
        """Handle disconnection event"""
        self.metrics['connection_state'] = 'disconnected'

    async def on_error(self, error):
        """Handle error event"""
        self.metrics['errors'].append({
            'time': datetime.now(),
            'error': str(error)
        })
        # Keep only last 10 errors
        self.metrics['errors'] = self.metrics['errors'][-10:]

    async def request_server_stats(self):
        """Request stats from server periodically"""
        while self.running:
            if self.client.state.value == 'authenticated':
                await self.client.request_stats()
            await asyncio.sleep(30)

    def draw_dashboard(self, stdscr):
        """Draw the monitoring dashboard"""
        curses.curs_set(0)  # Hide cursor
        stdscr.nodelay(1)    # Non-blocking input
        stdscr.timeout(100)  # Refresh every 100ms

        # Color pairs
        curses.init_pair(1, curses.COLOR_GREEN, curses.COLOR_BLACK)
        curses.init_pair(2, curses.COLOR_RED, curses.COLOR_BLACK)
        curses.init_pair(3, curses.COLOR_YELLOW, curses.COLOR_BLACK)
        curses.init_pair(4, curses.COLOR_CYAN, curses.COLOR_BLACK)

        while self.running:
            stdscr.clear()
            height, width = stdscr.getmaxyx()

            # Title
            title = "Signal WebSocket Monitor"
            stdscr.addstr(0, (width - len(title)) // 2, title, curses.A_BOLD)
            stdscr.addstr(1, 0, "=" * width)

            # Connection status
            row = 3
            stdscr.addstr(row, 0, "Connection: ", curses.A_BOLD)

            state = self.client.state.value
            if state == 'authenticated':
                stdscr.addstr(row, 12, f"● {state.upper()}", curses.color_pair(1) | curses.A_BOLD)
            elif state in ['connected', 'connecting']:
                stdscr.addstr(row, 12, f"● {state.upper()}", curses.color_pair(3))
            else:
                stdscr.addstr(row, 12, f"● {state.upper()}", curses.color_pair(2))

            # Server URL
            row += 1
            stdscr.addstr(row, 0, f"Server: {self.config['SIGNAL_WS_URL']}")

            # Statistics
            row += 2
            stdscr.addstr(row, 0, "Statistics:", curses.A_BOLD)
            row += 1
            stdscr.addstr(row, 2, f"Total Signals: {self.metrics['signals_total']:,}")

            row += 1
            if self.metrics['last_signal_time']:
                time_ago = (datetime.now() - self.metrics['last_signal_time']).total_seconds()
                stdscr.addstr(row, 2, f"Last Signal: {time_ago:.0f}s ago")
            else:
                stdscr.addstr(row, 2, "Last Signal: Never")

            # Calculate signals per minute
            row += 1
            if self.metrics['signals_per_minute']:
                recent_window = datetime.now() - timedelta(minutes=1)
                recent_signals = sum(
                    s['count'] for s in self.metrics['signals_per_minute']
                    if s['time'] > recent_window
                )
                stdscr.addstr(row, 2, f"Rate: {recent_signals} signals/min")

            # Client stats
            client_stats = self.client.get_stats()
            row += 1
            stdscr.addstr(row, 2, f"Bytes Received: {client_stats['total_bytes_received']:,}")
            row += 1
            stdscr.addstr(row, 2, f"Reconnections: {client_stats['reconnections']}")

            # Recent signals
            row += 2
            stdscr.addstr(row, 0, "Recent Signals:", curses.A_BOLD)
            row += 1

            for signal in self.metrics['recent_signals'][:5]:
                if row < height - 5:
                    signal_str = f"  {signal['symbol']:<10} Score: {signal['score']:.3f} Type: {signal['signal_type']}"
                    stdscr.addstr(row, 0, signal_str[:width-1])
                    row += 1

            # Errors (if any)
            if self.metrics['errors'] and row < height - 3:
                row += 1
                stdscr.addstr(row, 0, "Recent Errors:", curses.A_BOLD | curses.color_pair(2))
                row += 1
                for error in self.metrics['errors'][-3:]:
                    if row < height - 2:
                        error_str = f"  {error['error'][:width-5]}"
                        stdscr.addstr(row, 0, error_str, curses.color_pair(2))
                        row += 1

            # Footer
            footer = "Press 'q' to quit, 'r' to request signals, 's' for stats"
            stdscr.addstr(height - 1, 0, footer[:width-1], curses.A_DIM)

            # Handle input
            key = stdscr.getch()
            if key == ord('q'):
                self.running = False
            elif key == ord('r'):
                asyncio.create_task(self.client.request_signals())
            elif key == ord('s'):
                asyncio.create_task(self.client.request_stats())

            stdscr.refresh()

    async def run_monitor(self, stdscr):
        """Run the monitoring dashboard"""
        self.running = True

        # Start client
        client_task = asyncio.create_task(self.client.run())
        stats_task = asyncio.create_task(self.request_server_stats())

        # Run dashboard in thread
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.draw_dashboard, stdscr)

        # Cleanup
        self.running = False
        await self.client.stop()
        client_task.cancel()
        stats_task.cancel()

    def start(self):
        """Start the monitor with curses"""
        try:
            curses.wrapper(lambda stdscr: asyncio.run(self.run_monitor(stdscr)))
        except KeyboardInterrupt:
            print("\nMonitor stopped")


class SimpleMonitor:
    """Simple text-based monitor (no curses)"""

    def __init__(self, config: dict):
        self.config = config
        self.client = SignalWebSocketClient(config)
        self.running = False

        self.stats = {
            'signals_received': 0,
            'last_signal': None,
            'start_time': datetime.now()
        }

    async def on_signals(self, signals):
        """Process received signals"""
        self.stats['signals_received'] += len(signals)
        self.stats['last_signal'] = datetime.now()

        print(f"\n{'='*130}")
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Received {len(signals)} signals")
        print(f"{'='*130}")

        # Table header
        header = (
            f"{'#':<4} {'ID':<10} {'Symbol':<18} {'Action':<6} {'Week':<7} {'Month':<7} "
            f"{'Timestamp':<22} {'Created At':<22} {'Pair ID':<8} {'Exch ID':<8}"
        )
        print(header)
        print('-' * 130)

        # Table rows
        for i, signal in enumerate(signals, 1):
            row = (
                f"{i:<4} "
                f"{signal.get('id', 'N/A'):<10} "
                f"{signal.get('pair_symbol', 'N/A'):<18} "
                f"{signal.get('recommended_action', 'N/A'):<6} "
                f"{signal.get('score_week', 0):<7.2f} "
                f"{signal.get('score_month', 0):<7.2f} "
                f"{str(signal.get('timestamp', 'N/A'))[:21]:<22} "
                f"{str(signal.get('created_at', 'N/A'))[:21]:<22} "
                f"{signal.get('trading_pair_id', 'N/A'):<8} "
                f"{signal.get('exchange_id', 'N/A'):<8}"
            )
            print(row)

        print('=' * 130 + '\n')

    async def run(self):
        """Run simple monitor"""
        print("Signal WebSocket Monitor (Simple Mode)")
        print("=" * 50)
        print(f"Server: {self.config['SIGNAL_WS_URL']}")
        print("Press Ctrl+C to stop\n")

        self.client.set_callbacks(on_signals=self.on_signals)
        self.running = True

        # Start client
        client_task = asyncio.create_task(self.client.run())

        # Monitor loop
        while self.running:
            await asyncio.sleep(30)

            # Print periodic status
            uptime = (datetime.now() - self.stats['start_time']).total_seconds()
            rate = self.stats['signals_received'] / uptime if uptime > 0 else 0

            print(f"\n[Status] Uptime: {uptime:.0f}s, "
                  f"Signals: {self.stats['signals_received']}, "
                  f"Rate: {rate:.2f}/s, "
                  f"State: {self.client.state.value}")

        await self.client.stop()
        client_task.cancel()


def main():
    """Main entry point"""
    import argparse

    parser = argparse.ArgumentParser(description='Monitor Signal WebSocket Server')
    parser.add_argument('--url', default='ws://localhost:8765', help='WebSocket URL')
    parser.add_argument('--token', required=True, help='Authentication token')
    parser.add_argument('--simple', action='store_true', help='Use simple text mode')

    args = parser.parse_args()

    config = {
        'SIGNAL_WS_URL': args.url,
        'SIGNAL_WS_TOKEN': args.token,
        'AUTO_RECONNECT': True
    }

    try:
        if args.simple:
            monitor = SimpleMonitor(config)
            asyncio.run(monitor.run())
        else:
            monitor = SignalMonitor(config)
            monitor.start()
    except KeyboardInterrupt:
        print("\nMonitor stopped")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()