#!/usr/bin/env python3
"""
Optimized Signal WebSocket Server (Port 25374)
Broadcasts signals matching "Best Strategies" (total_pnl > 180%)
Includes optimized risk parameters (SL, TS)
"""

import asyncio
import json
import logging
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Set, Dict, Optional, List
import signal
import sys
import os

import asyncpg
import websockets
from dotenv import load_dotenv

# Load environment variables
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(os.path.dirname(current_dir), 'win_rate', '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv()

# Logging setup
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('optimized_signal_ws.log')
    ]
)
logger = logging.getLogger('OptimizedSignalWS')


class OptimizedSignalServer:
    """
    WebSocket server for streaming OPTIMIZED trading signals
    Port: 25374
    Logic: Matches signals against strategies with total_pnl > 180%
    """

    def __init__(self, config: dict):
        # Server settings
        self.host = config.get('WS_SERVER_HOST', '0.0.0.0')
        self.port = int(config.get('WS_SERVER_PORT', 25374))
        self.auth_token = config.get('WS_AUTH_TOKEN')

        # Database settings
        self.db_config = {
            'host': config.get('DB_HOST', 'localhost'),
            'port': int(config.get('DB_PORT', 5432)),
            'database': config.get('DB_NAME'),
            'user': config.get('DB_USER'),
            'password': config.get('DB_PASSWORD')
        }

        # Query settings
        self.query_interval = int(config.get('QUERY_INTERVAL_SECONDS', 3))
        self.signal_window_minutes = int(config.get('SIGNAL_WINDOW_MINUTES', 30))
        self.min_strategy_pnl = float(config.get('MIN_STRATEGY_PNL', 180))

        # Hybrid mode: NOTIFY + Polling
        self.use_notify = config.get('USE_NOTIFY', 'true').lower() == 'true'
        self.notify_channel = config.get('NOTIFY_CHANNEL', 'new_signals')
        self.lightweight_check_interval = int(config.get('LIGHTWEIGHT_CHECK_INTERVAL', 1))
        self.notify_fallback_interval = int(config.get('NOTIFY_FALLBACK_INTERVAL', 60))

        # Notify state
        self.notify_available = False
        self.notify_connection: Optional[asyncpg.Connection] = None

        # Change tracking
        self.last_max_id = 0
        
        # Client management
        self.connected_clients: Set = set()
        self.authenticated_clients: Set = set()
        self.client_info: Dict = {}

        # State
        self.db_pool: Optional[asyncpg.Pool] = None
        self.running = False
        self.last_signals: List[dict] = []
        self.stats = {
            'queries_executed': 0,
            'signals_sent': 0,
            'errors': 0,
            'start_time': datetime.now()
        }

        logger.info(f"Optimized Signal Server initialized on {self.host}:{self.port}")
        logger.info(f"Strategy Filter: total_pnl > {self.min_strategy_pnl}%")

    def hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def build_signal_query(self) -> str:
        """
        Constructs the complex SQL query to match signals with best strategies.
        Logic is identical to yesterday/1_select_yesterday_signals.py
        """
        query_template = r"""
        WITH best_strategies AS (
            -- Get top strategies with total_pnl > threshold
            SELECT DISTINCT ON (strategy_name, signal_type, market_regime)
                strategy_name,
                signal_type,
                market_regime,
                sl_pct,
                ts_activation_pct,
                ts_callback_pct,
                total_pnl_pct,
                -- Extract patterns array from strategy_name format: "['PAT1', 'PAT2']|TYPE|REGIME"
                string_to_array(
                    regexp_replace(
                        split_part(strategy_name, '|', 1),  -- Get ['PAT1', 'PAT2'] part
                        '[\[\]'']',  -- Remove brackets and quotes
                        '',
                        'g'
                    ),
                    ', '  -- Split by comma-space
                ) as required_patterns
            FROM optimization.best_parameters
            WHERE total_pnl_pct > {min_pnl}
            ORDER BY
                strategy_name,
                signal_type,
                market_regime,
                total_pnl_pct DESC
        ),
        recent_signals AS (
            -- Get signals from recent window
            SELECT
                sh.id as signal_id,
                sh.pair_symbol,
                sh.timestamp as signal_timestamp,
                sh.total_score,
                sh.score_week,
                sh.score_month,
                sh.created_at,
                tp.id as trading_pair_id,
                tp.exchange_id,
                
                -- Aggregate patterns
                ARRAY_AGG(DISTINCT sp.pattern_type || '_' || sp.timeframe) as patterns,
                
                -- Get market regime
                mr.regime as market_regime
                
            FROM fas_v2.scoring_history sh
            JOIN fas_v2.sh_patterns shp ON shp.scoring_history_id = sh.id
            JOIN fas_v2.signal_patterns sp ON sp.id = shp.signal_patterns_id
            INNER JOIN public.trading_pairs tp ON tp.pair_symbol = sh.pair_symbol
            LEFT JOIN fas_v2.sh_regime shr_regime ON shr_regime.scoring_history_id = sh.id
            LEFT JOIN fas_v2.market_regime mr ON mr.id = shr_regime.signal_regime_id
            WHERE sh.timestamp >= NOW() - INTERVAL '%s minutes'
                AND tp.exchange_id = 1  -- Binance Futures Only
                AND tp.contract_type_id = 1
                AND tp.is_active = true
            GROUP BY sh.id, sh.pair_symbol, sh.timestamp, sh.total_score, sh.score_week, sh.score_month, sh.created_at, tp.id, tp.exchange_id, mr.regime
            HAVING COUNT(DISTINCT sp.id) >= 2  -- Multi-pattern only
        )
        SELECT DISTINCT ON (rs.signal_id)
            rs.signal_id,
            rs.pair_symbol,
            rs.signal_timestamp,
            rs.created_at,
            rs.total_score,
            rs.score_week,
            rs.score_month,
            rs.market_regime,
            rs.trading_pair_id,
            rs.exchange_id,
            
            -- Optimized Parameters
            bs.strategy_name,
            bs.signal_type as strategy_signal_type,
            bs.sl_pct,
            bs.ts_activation_pct,
            bs.ts_callback_pct,
            bs.total_pnl_pct as strategy_pnl
            
        FROM recent_signals rs
        JOIN best_strategies bs ON (
            bs.market_regime = rs.market_regime
            AND rs.patterns @> bs.required_patterns  -- EXACT pattern match
        )
        WHERE rs.market_regime IS NOT NULL
        ORDER BY rs.signal_id, bs.total_pnl_pct DESC
        """
        return query_template.format(min_pnl=self.min_strategy_pnl)

    async def init_db(self):
        """Initialize DB pool"""
        try:
            self.db_pool = await asyncpg.create_pool(
                **self.db_config,
                min_size=2,
                max_size=10,
                command_timeout=60
            )
            logger.info("Database pool created successfully")
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    async def init_notify_listener(self):
        """Initialize PostgreSQL LISTEN/NOTIFY"""
        if not self.use_notify:
            return False

        try:
            self.notify_connection = await asyncpg.connect(**self.db_config)
            await self.notify_connection.add_listener(
                self.notify_channel,
                self.on_notify_received
            )
            self.notify_available = True
            logger.info(f"✓ PostgreSQL NOTIFY listener active on '{self.notify_channel}'")
            return True
        except Exception as e:
            logger.warning(f"Failed to setup NOTIFY: {e}")
            self.notify_available = False
            return False

    async def on_notify_received(self, connection, pid, channel, payload):
        """Handle DB notification"""
        try:
            if payload:
                logger.info(f"⚡ NOTIFY received: {payload}")
            await self.do_full_query_and_broadcast()
        except Exception as e:
            logger.error(f"Error processing NOTIFY: {e}")

    async def fetch_signals(self) -> List[dict]:
        """Fetch optimized signals from DB"""
        try:
            async with self.db_pool.acquire() as conn:
                query = self.build_signal_query()
                rows = await conn.fetch(query % self.signal_window_minutes)

                signals = []
                for row in rows:
                    signal = {
                        'id': row['signal_id'],
                        'trading_pair_id': row['trading_pair_id'] if row['trading_pair_id'] is not None else 'N/A',
                        'pair_symbol': row['pair_symbol'] if row['pair_symbol'] is not None else '',
                        'total_score': float(row['total_score']) if row['total_score'] else 0,
                        'score_week': float(row['score_week']) if row['score_week'] is not None else 0.0,
                        'score_month': float(row['score_month']) if row['score_month'] is not None else 0.0,
                        'timestamp': row['signal_timestamp'].isoformat() if row['signal_timestamp'] else None,
                        'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                        'exchange_id': row['exchange_id'] if row['exchange_id'] is not None else 'N/A',
                        'contract_type_id': 1,  # Binance Futures
                        'patterns': [],  # Can be added if needed
                        'timeframes': [],  # Can be added if needed
                        
                        # Parameters in client format (matching high_score_signal_server)
                        'recommended_action': row['strategy_signal_type'] if row['strategy_signal_type'] is not None else 'BUY',  # From best_parameters
                        'score_week_filter': float(row['score_week']) if row['score_week'] is not None else 0.0,
                        'score_month_filter': float(row['score_month']) if row['score_month'] is not None else 0.0,
                        'max_trades_filter': 10,
                        'stop_loss_filter': float(row['sl_pct']) if row['sl_pct'] is not None else 0.0,
                        'trailing_activation_filter': float(row['ts_activation_pct']) if row['ts_activation_pct'] is not None else 0.0,
                        'trailing_distance_filter': float(row['ts_callback_pct']) if row['ts_callback_pct'] is not None else 0.0,
                        
                        # Additional fields for info
                        'strategy_name': row['strategy_name'] if row['strategy_name'] is not None else '',
                        'market_regime': row['market_regime'] if row['market_regime'] is not None else '',
                        'strategy_pnl': float(row['strategy_pnl']) if row['strategy_pnl'] is not None else 0.0
                    }
                    signals.append(signal)

                self.stats['queries_executed'] += 1
                logger.debug(f"Fetched {len(signals)} optimized signals")
                return signals

        except Exception as e:
            logger.error(f"Error fetching signals: {e}")
            self.stats['errors'] += 1
            return []

    async def check_for_changes_lightweight(self) -> bool:
        """Lightweight check for new signals"""
        try:
            async with self.db_pool.acquire() as conn:
                result = await conn.fetchrow("""
                    SELECT MAX(id) as max_id
                    FROM fas_v2.scoring_history
                    WHERE timestamp >= NOW() - INTERVAL '%s minutes'
                """ % self.signal_window_minutes)

                if not result or not result['max_id']:
                    return False

                max_id = result['max_id']
                has_changes = max_id > self.last_max_id
                
                if has_changes:
                    self.last_max_id = max_id
                    
                return has_changes

        except Exception as e:
            logger.error(f"Error in lightweight check: {e}")
            return True

    async def do_full_query_and_broadcast(self):
        """Execute full query and broadcast if signals found"""
        try:
            signals = await self.fetch_signals()
            self.last_signals = signals
            await self.broadcast_signals(signals)
            
            if signals:
                logger.info(f"📡 Broadcast {len(signals)} optimized signals")
        except Exception as e:
            logger.error(f"Error in broadcast: {e}")

    async def broadcast_signals(self, signals: List[dict]):
        """Send signals to authenticated clients"""
        if not self.authenticated_clients:
            return

        message = json.dumps({
            'type': 'signals',
            'timestamp': datetime.now().isoformat(),
            'count': len(signals),
            'data': signals
        })

        disconnected = set()
        for client in self.authenticated_clients:
            try:
                await client.send(message)
                self.stats['signals_sent'] += 1
            except Exception:
                disconnected.add(client)

        for client in disconnected:
            await self.disconnect_client(client)

    async def handle_client(self, websocket):
        """Handle new client connection"""
        self.connected_clients.add(websocket)
        client_ip = websocket.remote_address[0] if websocket.remote_address else 'unknown'
        
        self.client_info[websocket] = {
            'ip': client_ip,
            'connected_at': datetime.now(),
            'authenticated': False
        }
        
        logger.info(f"Client connected: {client_ip}")

        try:
            await websocket.send(json.dumps({
                'type': 'auth_required',
                'message': 'Please authenticate'
            }))

            auth_task = asyncio.create_task(self.wait_for_auth(websocket))

            async for message in websocket:
                await self.handle_message(websocket, message)

        except Exception as e:
            logger.error(f"Client error {client_ip}: {e}")
        finally:
            await self.disconnect_client(websocket)
            auth_task.cancel()

    async def wait_for_auth(self, websocket):
        """Auth timeout"""
        await asyncio.sleep(30)
        if websocket in self.connected_clients and websocket not in self.authenticated_clients:
            await websocket.close()

    async def handle_message(self, websocket, message: str):
        """Handle client message"""
        try:
            data = json.loads(message)
            msg_type = data.get('type')

            if msg_type == 'auth':
                await self.handle_auth(websocket, data)
            elif msg_type == 'ping':
                await websocket.send(json.dumps({'type': 'pong'}))
            elif msg_type == 'get_signals':
                if websocket in self.authenticated_clients:
                    await websocket.send(json.dumps({
                        'type': 'signals',
                        'data': self.last_signals
                    }))

        except Exception as e:
            logger.error(f"Message error: {e}")

    async def handle_auth(self, websocket, data: dict):
        """Handle authentication"""
        token = data.get('token')
        if not token:
            return

        if self.hash_token(token) == self.auth_token:
            self.authenticated_clients.add(websocket)
            self.client_info[websocket]['authenticated'] = True
            
            await websocket.send(json.dumps({
                'type': 'auth_success',
                'server': 'OptimizedSignalServer',
                'port': self.port
            }))
            
            if self.last_signals:
                await websocket.send(json.dumps({
                    'type': 'signals',
                    'data': self.last_signals
                }))
        else:
            await websocket.close()

    async def disconnect_client(self, websocket):
        """Disconnect client"""
        self.connected_clients.discard(websocket)
        self.authenticated_clients.discard(websocket)
        if websocket in self.client_info:
            del self.client_info[websocket]

    async def smart_query_loop(self):
        """Main query loop"""
        while self.running:
            try:
                if self.notify_available:
                    await asyncio.sleep(self.notify_fallback_interval)
                    if await self.check_for_changes_lightweight():
                        await self.do_full_query_and_broadcast()
                else:
                    has_changes = await self.check_for_changes_lightweight()
                    if has_changes:
                        await self.do_full_query_and_broadcast()
                    await asyncio.sleep(self.lightweight_check_interval)
            except Exception as e:
                logger.error(f"Loop error: {e}")
                await asyncio.sleep(5)

    async def start(self):
        """Start server"""
        logger.info("Starting Optimized Signal Server...")
        await self.init_db()
        await self.init_notify_listener()
        
        self.last_signals = await self.fetch_signals()
        logger.info(f"Initial signals: {len(self.last_signals)}")
        
        self.running = True
        query_task = asyncio.create_task(self.smart_query_loop())

        async with websockets.serve(self.handle_client, self.host, self.port):
            logger.info(f"Listening on port {self.port}")
            try:
                await asyncio.Future()
            finally:
                self.running = False
                query_task.cancel()
                if self.db_pool:
                    await self.db_pool.close()


def main():
    # Configuration
    config = {
        'WS_SERVER_HOST': os.getenv('WS_SERVER_HOST', '0.0.0.0'),
        'WS_SERVER_PORT': os.getenv('OPTIMIZED_WS_PORT', '25374'),
        'WS_AUTH_TOKEN': hashlib.sha256(
            os.getenv('WS_AUTH_PASSWORD', 'change_me_please').encode()
        ).hexdigest(),
        'DB_HOST': os.getenv('DB_HOST', 'localhost'),
        'DB_PORT': os.getenv('DB_PORT', '5432'),
        'DB_NAME': os.getenv('DB_NAME'),
        'DB_USER': os.getenv('DB_USER'),
        'DB_PASSWORD': os.getenv('DB_PASSWORD'),
        'MIN_STRATEGY_PNL': '180'
    }

    server = OptimizedSignalServer(config)
    
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        pass
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
