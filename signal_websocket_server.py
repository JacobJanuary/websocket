#!/usr/bin/env python3
"""
WebSocket сервер для трансляции торговых сигналов из PostgreSQL
Обеспечивает безопасную изоляцию БД от прямого доступа ботов
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

import asyncpg
import websockets

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('signal_ws_server.log')
    ]
)
logger = logging.getLogger('SignalWSServer')


class SignalWebSocketServer:
    """
    WebSocket сервер для стриминга торговых сигналов
    Поддерживает гибридный режим работы:
    - PostgreSQL LISTEN/NOTIFY (event-driven, < 10ms latency)
    - Lightweight polling (fallback, 1 sec interval)
    """

    def __init__(self, config: dict):
        # Настройки сервера
        self.host = config.get('WS_SERVER_HOST', '0.0.0.0')
        self.port = int(config.get('WS_SERVER_PORT', 8765))
        self.auth_token = config.get('WS_AUTH_TOKEN')  # Хешированный токен

        # Настройки БД
        self.db_config = {
            'host': config.get('DB_HOST', 'localhost'),
            'port': int(config.get('DB_PORT', 5432)),
            'database': config.get('DB_NAME'),
            'user': config.get('DB_USER'),
            'password': config.get('DB_PASSWORD')
        }

        # Настройки запроса
        self.query_interval = int(config.get('QUERY_INTERVAL_SECONDS', 3))
        self.signal_window_minutes = int(config.get('SIGNAL_WINDOW_MINUTES', 30))

        # Гибридный режим: NOTIFY + Polling
        self.use_notify = config.get('USE_NOTIFY', 'true').lower() == 'true'
        self.notify_channel = config.get('NOTIFY_CHANNEL', 'new_signals')
        self.lightweight_check_interval = int(config.get('LIGHTWEIGHT_CHECK_INTERVAL', 1))
        self.notify_fallback_interval = int(config.get('NOTIFY_FALLBACK_INTERVAL', 60))

        # Управление биржами
        self.binance_enabled = config.get('BINANCE_ENABLED', 'true').lower() == 'true'
        self.bybit_enabled = config.get('BYBIT_ENABLED', 'true').lower() == 'true'

        # Состояние NOTIFY
        self.notify_available = False
        self.notify_connection: Optional[asyncpg.Connection] = None

        # Отслеживание изменений для lightweight проверок
        self.last_max_id = 0
        self.last_check_timestamp = None

        # Управление подключениями
        self.connected_clients: Set = set()
        self.authenticated_clients: Set = set()
        self.client_info: Dict = {}

        # Состояние
        self.db_pool: Optional[asyncpg.Pool] = None
        self.running = False
        self.last_signals: List[dict] = []
        self.stats = {
            'queries_executed': 0,
            'signals_sent': 0,
            'errors': 0,
            'start_time': datetime.now()
        }

        # Валидация: хотя бы одна биржа должна быть включена
        if not self.binance_enabled and not self.bybit_enabled:
            raise ValueError("At least one exchange must be enabled (BINANCE_ENABLED or BYBIT_ENABLED)")

        logger.info(f"Signal WebSocket Server initialized on {self.host}:{self.port}")
        logger.info(f"Hybrid mode: NOTIFY={'enabled' if self.use_notify else 'disabled'}, "
                   f"Lightweight check interval={self.lightweight_check_interval}s")
        logger.info(f"Enabled exchanges: "
                   f"Binance={'enabled' if self.binance_enabled else 'disabled'}, "
                   f"Bybit={'enabled' if self.bybit_enabled else 'disabled'}")

    def hash_token(self, token: str) -> str:
        """Хеширование токена для безопасного сравнения"""
        return hashlib.sha256(token.encode()).hexdigest()

    def build_signal_query(self) -> str:
        """
        Формирует динамический SQL запрос в зависимости от включенных бирж
        Возвращает запрос с placeholder '%s' для signal_window_minutes
        """
        # Определяем какие exchange_id включены
        enabled_exchanges = []
        if self.binance_enabled:
            enabled_exchanges.append('1')
        if self.bybit_enabled:
            enabled_exchanges.append('2')

        # Формируем список для WHERE IN clause
        exchange_filter = ', '.join(enabled_exchanges)

        # Базовый SQL запрос (тот же что был, но с дополнительным фильтром)
        query = f"""
-- 1. CTE для поиска ЛУЧШЕГО ID для Binance (по вашей новой логике)
WITH best_binance_id AS (
    WITH FilteredSummaries AS (
        SELECT DISTINCT ON (total_pnl_usd)
            summary_id,
            win_rate,
            total_pnl_usd
        FROM
            web.backtest_summary_binance
        WHERE
            total_pnl_usd >= (
                SELECT MAX(total_pnl_usd)
                FROM web.backtest_summary_binance
            ) * 0.95
        ORDER BY
            total_pnl_usd DESC,
            win_rate DESC
    )
    SELECT
        summary_id
    FROM
        FilteredSummaries
    ORDER BY
        win_rate DESC
    LIMIT 1
),

-- 2. CTE для поиска ЛУЧШЕГО ID для Bybit (по вашей новой логике)
best_bybit_id AS (
    WITH FilteredSummaries AS (
        SELECT DISTINCT ON (total_pnl_usd)
            summary_id,
            win_rate,
            total_pnl_usd
        FROM
            web.backtest_summary_bybit
        WHERE
            total_pnl_usd >= (
                SELECT MAX(total_pnl_usd)
                FROM web.backtest_summary_bybit
            ) * 0.95
        ORDER BY
            total_pnl_usd DESC,
            win_rate DESC
    )
    SELECT
        summary_id
    FROM
        FilteredSummaries
    ORDER BY
        win_rate DESC
    LIMIT 1
),

-- 3. Теперь создаем CTE с ПАРАМЕТРАМИ, используя найденные ID
all_best_params AS (
    ( -- Параметры для Binance
        SELECT
            1 AS exchange_id,
            score_week_filter,
            score_month_filter,
            max_trades_filter,
            stop_loss_filter,
            trailing_activation_filter,
            trailing_distance_filter
        FROM web.backtest_summary_binance
        -- Используем ID из CTE 1
        WHERE summary_id = (SELECT summary_id FROM best_binance_id)
    )

    UNION ALL

    ( -- Параметры для Bybit
        SELECT
            2 AS exchange_id,
            score_week_filter,
            score_month_filter,
            max_trades_filter,
            stop_loss_filter,
            trailing_activation_filter,
            trailing_distance_filter
        FROM web.backtest_summary_bybit
        -- Используем ID из CTE 2
        WHERE summary_id = (SELECT summary_id FROM best_bybit_id)
    )
)

-- 4. Основной запрос к сигналам
SELECT
    sc.id,
    sc.pair_symbol,
    sc.recommended_action,
    sc.score_week,
    sc.score_month,
    sc.timestamp,
    sc.created_at,
    sc.trading_pair_id,
    tp.exchange_id,

    -- 5. Выводим параметры, которые "приехали" из CTE 3
    bp.score_week_filter,
    bp.score_month_filter,
    bp.max_trades_filter,
    bp.stop_loss_filter,
    bp.trailing_activation_filter,
    bp.trailing_distance_filter

FROM fas_v2.scoring_history AS sc
JOIN public.trading_pairs AS tp ON sc.trading_pair_id = tp.id
JOIN all_best_params AS bp ON tp.exchange_id = bp.exchange_id

WHERE
    sc.timestamp >= now() - INTERVAL '%s minutes'
    AND sc.is_active = true
    AND tp.is_active = true
    AND sc.score_week > bp.score_week_filter
    AND sc.score_month > bp.score_month_filter
    AND EXTRACT(HOUR FROM sc.timestamp) NOT BETWEEN 0 AND 1
    AND tp.exchange_id IN ({exchange_filter})
ORDER BY sc.score_week DESC NULLS LAST, sc.timestamp DESC;
"""
        return query

    async def init_db(self):
        """Инициализация пула соединений с БД"""
        try:
            self.db_pool = await asyncpg.create_pool(
                **self.db_config,
                min_size=2,
                max_size=10,
                command_timeout=60
            )
            logger.info("Database pool created successfully")

            # Тестовый запрос
            async with self.db_pool.acquire() as conn:
                result = await conn.fetchval("SELECT 1")
                if result == 1:
                    logger.info("Database connection verified")

        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    async def init_notify_listener(self):
        """
        Инициализация PostgreSQL LISTEN/NOTIFY
        Создает отдельное соединение для получения событий из БД
        """
        if not self.use_notify:
            logger.info("PostgreSQL NOTIFY disabled in configuration")
            return False

        try:
            # Создаем отдельное соединение для LISTEN
            self.notify_connection = await asyncpg.connect(**self.db_config)

            # Подписываемся на канал уведомлений
            await self.notify_connection.add_listener(
                self.notify_channel,
                self.on_notify_received
            )

            self.notify_available = True
            logger.info(f"✓ PostgreSQL NOTIFY listener active on channel '{self.notify_channel}'")
            logger.info(f"  Mode: Event-driven (real-time < 10ms)")
            return True

        except Exception as e:
            logger.warning(f"Failed to setup NOTIFY listener: {e}")
            logger.info(f"  Falling back to polling mode (interval: {self.lightweight_check_interval}s)")
            self.notify_available = False
            return False

    async def on_notify_received(self, connection, pid, channel, payload):
        """
        Callback вызывается при получении NOTIFY от PostgreSQL
        Обеспечивает мгновенную реакцию на новые сигналы (< 10ms)
        """
        try:
            # Парсим payload от триггера
            if payload:
                data = json.loads(payload)
                logger.info(f"⚡ NOTIFY received: event={data.get('event')}, "
                          f"id={data.get('id')}, symbol={data.get('pair_symbol')}, "
                          f"score={data.get('score_week')}")
            else:
                logger.info(f"⚡ NOTIFY received from PID {pid}")

            # Выполняем полный запрос и broadcast
            await self.do_full_query_and_broadcast()

        except json.JSONDecodeError:
            logger.warning(f"Invalid JSON in NOTIFY payload: {payload[:100]}")
            # Все равно делаем запрос
            await self.do_full_query_and_broadcast()
        except Exception as e:
            logger.error(f"Error processing NOTIFY: {e}")
            self.stats['errors'] += 1

    async def fetch_signals(self) -> List[dict]:
        """Получение сигналов из БД"""
        try:
            async with self.db_pool.acquire() as conn:
                # Формируем динамический запрос на основе включенных бирж
                query = self.build_signal_query()

                # Выполняем запрос
                rows = await conn.fetch(
                    query % self.signal_window_minutes
                )

                # Преобразуем в словари (15 полей: 9 основных + 6 из backtest)
                signals = []
                for row in rows:
                    signal = {
                        'id': row['id'],
                        'pair_symbol': row['pair_symbol'],
                        'recommended_action': row['recommended_action'],
                        'score_week': float(row['score_week']) if row['score_week'] else 0,
                        'score_month': float(row['score_month']) if row['score_month'] else 0,
                        'timestamp': row['timestamp'].isoformat() if row['timestamp'] else None,
                        'created_at': row['created_at'].isoformat() if row['created_at'] else None,
                        'trading_pair_id': row['trading_pair_id'],
                        'exchange_id': row['exchange_id'],
                        # Параметры из backtest_summary
                        'score_week_filter': float(row['score_week_filter']) if row['score_week_filter'] else None,
                        'score_month_filter': float(row['score_month_filter']) if row['score_month_filter'] else None,
                        'max_trades_filter': int(row['max_trades_filter']) if row['max_trades_filter'] else None,
                        'stop_loss_filter': float(row['stop_loss_filter']) if row['stop_loss_filter'] else None,
                        'trailing_activation_filter': float(row['trailing_activation_filter']) if row['trailing_activation_filter'] else None,
                        'trailing_distance_filter': float(row['trailing_distance_filter']) if row['trailing_distance_filter'] else None
                    }
                    signals.append(signal)

                self.stats['queries_executed'] += 1
                logger.debug(f"Fetched {len(signals)} signals from database")

                return signals

        except Exception as e:
            logger.error(f"Error fetching signals: {e}")
            self.stats['errors'] += 1
            return []

    async def check_for_changes_lightweight(self) -> bool:
        """
        Легковесная проверка: появились ли новые сигналы?
        Запрос выполняется за ~1-2ms вместо ~50-100ms полного запроса
        Проверяет только MAX(id) и MAX(timestamp)
        """
        try:
            async with self.db_pool.acquire() as conn:
                result = await conn.fetchrow("""
                    SELECT
                        MAX(sc.id) as max_id,
                        MAX(sc.timestamp) as max_timestamp,
                        COUNT(*) as total_count
                    FROM fas_v2.scoring_history sc
                    JOIN public.trading_pairs tp ON sc.trading_pair_id = tp.id
                    WHERE sc.timestamp >= now() - INTERVAL '%s minutes'
                        AND sc.is_active = true
                        AND tp.is_active = true
                        AND sc.score_week > 50
                        AND sc.score_month > 50
                """ % self.signal_window_minutes)

                if not result or not result['max_id']:
                    return False

                max_id = result['max_id']
                max_ts = result['max_timestamp']

                # Проверяем изменения
                has_changes = (
                    max_id > self.last_max_id or
                    (max_ts and max_ts != self.last_check_timestamp)
                )

                if has_changes:
                    self.last_max_id = max_id
                    self.last_check_timestamp = max_ts
                    logger.debug(f"Changes detected: max_id={max_id}, count={result['total_count']}")

                return has_changes

        except Exception as e:
            logger.error(f"Error in lightweight check: {e}")
            return True  # При ошибке делаем полный запрос

    async def do_full_query_and_broadcast(self):
        """
        Выполняет полный запрос сигналов и рассылку всем клиентам
        Используется как при NOTIFY, так и при обнаружении изменений в polling mode
        """
        try:
            signals = await self.fetch_signals()
            self.last_signals = signals
            await self.broadcast_signals(signals)

            # Подсчет сигналов по биржам для логирования
            binance_count = len([s for s in signals if s['exchange_id'] == 1])
            bybit_count = len([s for s in signals if s['exchange_id'] == 2])

            logger.info(f"📡 Broadcast {len(signals)} signals to {len(self.authenticated_clients)} clients "
                       f"(Binance: {binance_count}, Bybit: {bybit_count})")
        except Exception as e:
            logger.error(f"Error in full query and broadcast: {e}")
            self.stats['errors'] += 1

    async def broadcast_signals(self, signals: List[dict]):
        """Отправка сигналов всем аутентифицированным клиентам"""
        if not self.authenticated_clients:
            return

        # Подготовка сообщения
        message = json.dumps({
            'type': 'signals',
            'timestamp': datetime.now().isoformat(),
            'count': len(signals),
            'data': signals
        })

        # Отправка всем аутентифицированным клиентам
        disconnected = set()

        for client in self.authenticated_clients:
            try:
                await client.send(message)
                self.stats['signals_sent'] += 1
            except websockets.exceptions.ConnectionClosed:
                disconnected.add(client)
            except Exception as e:
                logger.error(f"Error sending to client: {e}")
                disconnected.add(client)

        # Удаление отключенных клиентов
        for client in disconnected:
            await self.disconnect_client(client)

    async def handle_client(self, websocket):
        """Обработка подключения клиента"""
        # Регистрация клиента
        self.connected_clients.add(websocket)
        client_ip = websocket.remote_address[0] if websocket.remote_address else 'unknown'

        self.client_info[websocket] = {
            'ip': client_ip,
            'connected_at': datetime.now(),
            'authenticated': False
        }

        logger.info(f"New client connected from {client_ip}")

        try:
            # Отправляем запрос аутентификации
            await websocket.send(json.dumps({
                'type': 'auth_required',
                'message': 'Please authenticate with your token'
            }))

            # Ждем аутентификацию (30 секунд таймаут)
            auth_task = asyncio.create_task(self.wait_for_auth(websocket))

            # Основной цикл обработки сообщений
            async for message in websocket:
                await self.handle_message(websocket, message)

        except websockets.exceptions.ConnectionClosed:
            logger.info(f"Client {client_ip} disconnected")
        except Exception as e:
            logger.error(f"Error handling client {client_ip}: {e}")
        finally:
            await self.disconnect_client(websocket)
            auth_task.cancel()

    async def wait_for_auth(self, websocket):
        """Ожидание аутентификации с таймаутом"""
        await asyncio.sleep(30)

        if websocket in self.connected_clients and websocket not in self.authenticated_clients:
            logger.warning(f"Client {self.client_info[websocket]['ip']} failed to authenticate in time")
            await websocket.send(json.dumps({
                'type': 'error',
                'message': 'Authentication timeout'
            }))
            await websocket.close()

    async def handle_message(self, websocket, message: str):
        """Обработка сообщения от клиента"""
        try:
            data = json.loads(message)
            msg_type = data.get('type')

            if msg_type == 'auth':
                await self.handle_auth(websocket, data)
            elif msg_type == 'ping':
                await websocket.send(json.dumps({'type': 'pong'}))
            elif msg_type == 'get_stats':
                await self.send_stats(websocket)
            elif msg_type == 'get_signals':
                # Немедленная отправка последних сигналов
                if websocket in self.authenticated_clients:
                    await websocket.send(json.dumps({
                        'type': 'signals',
                        'timestamp': datetime.now().isoformat(),
                        'count': len(self.last_signals),
                        'data': self.last_signals
                    }))
            else:
                logger.warning(f"Unknown message type: {msg_type}")

        except json.JSONDecodeError:
            logger.error(f"Invalid JSON from client: {message[:100]}")
        except Exception as e:
            logger.error(f"Error handling message: {e}")

    async def handle_auth(self, websocket, data: dict):
        """Обработка аутентификации"""
        token = data.get('token')

        if not token:
            await websocket.send(json.dumps({
                'type': 'auth_failed',
                'message': 'Token required'
            }))
            return

        # Проверка токена
        if self.hash_token(token) == self.auth_token:
            self.authenticated_clients.add(websocket)
            self.client_info[websocket]['authenticated'] = True

            logger.info(f"Client {self.client_info[websocket]['ip']} authenticated successfully")

            await websocket.send(json.dumps({
                'type': 'auth_success',
                'message': 'Authentication successful',
                'query_interval': self.query_interval,
                'signal_window': self.signal_window_minutes
            }))

            # Отправляем последние сигналы сразу после аутентификации
            if self.last_signals:
                await websocket.send(json.dumps({
                    'type': 'signals',
                    'timestamp': datetime.now().isoformat(),
                    'count': len(self.last_signals),
                    'data': self.last_signals
                }))
        else:
            logger.warning(f"Authentication failed for {self.client_info[websocket]['ip']}")
            await websocket.send(json.dumps({
                'type': 'auth_failed',
                'message': 'Invalid token'
            }))
            await asyncio.sleep(1)
            await websocket.close()

    async def send_stats(self, websocket):
        """Отправка статистики сервера"""
        if websocket not in self.authenticated_clients:
            return

        uptime = (datetime.now() - self.stats['start_time']).total_seconds()

        await websocket.send(json.dumps({
            'type': 'stats',
            'uptime_seconds': uptime,
            'connected_clients': len(self.connected_clients),
            'authenticated_clients': len(self.authenticated_clients),
            'queries_executed': self.stats['queries_executed'],
            'signals_sent': self.stats['signals_sent'],
            'errors': self.stats['errors'],
            'last_query': self.last_signals[0]['timestamp'] if self.last_signals else None
        }))

    async def disconnect_client(self, websocket):
        """Отключение клиента"""
        self.connected_clients.discard(websocket)
        self.authenticated_clients.discard(websocket)

        if websocket in self.client_info:
            logger.info(f"Client {self.client_info[websocket]['ip']} disconnected")
            del self.client_info[websocket]

    async def smart_query_loop(self):
        """
        Умный цикл опроса с адаптивной стратегией:
        - Если NOTIFY доступен: fallback проверка раз в 60 сек (safety net)
        - Если NOTIFY недоступен: легковесные проверки каждую секунду
        """
        last_full_query = datetime.now()

        while self.running:
            try:
                if self.notify_available:
                    # ===== NOTIFY MODE =====
                    # NOTIFY обрабатывает события моментально
                    # Здесь только fallback проверка на случай пропуска NOTIFY
                    await asyncio.sleep(self.notify_fallback_interval)

                    logger.debug("Fallback check (NOTIFY mode, safety net)")
                    if await self.check_for_changes_lightweight():
                        await self.do_full_query_and_broadcast()
                        last_full_query = datetime.now()

                else:
                    # ===== POLLING MODE =====
                    # Легковесная проверка на изменения
                    has_changes = await self.check_for_changes_lightweight()

                    # Принудительный полный запрос каждые N секунд (safety net)
                    time_since_last = (datetime.now() - last_full_query).total_seconds()
                    force_full_query = time_since_last >= self.query_interval

                    if has_changes or force_full_query:
                        await self.do_full_query_and_broadcast()
                        last_full_query = datetime.now()
                    else:
                        logger.debug("No changes detected, skipping full query")

                    # Короткая пауза до следующей проверки
                    await asyncio.sleep(self.lightweight_check_interval)

            except Exception as e:
                logger.error(f"Error in smart query loop: {e}")
                self.stats['errors'] += 1
                await asyncio.sleep(5)  # Короткая пауза при ошибке

    async def start(self):
        """Запуск сервера с гибридным режимом"""
        logger.info("=" * 70)
        logger.info("Starting Signal WebSocket Server (Hybrid Mode)")
        logger.info("=" * 70)

        # Инициализация БД
        await self.init_db()

        # Попытка инициализации NOTIFY
        await self.init_notify_listener()

        # Загрузка начальных сигналов
        self.last_signals = await self.fetch_signals()
        logger.info(f"✓ Initial signals loaded: {len(self.last_signals)} signals")

        self.running = True

        # Вывод режима работы
        if self.notify_available:
            logger.info("🚀 Running in NOTIFY mode (event-driven)")
            logger.info(f"   - Latency: < 10ms")
            logger.info(f"   - Fallback check: every {self.notify_fallback_interval}s")
        else:
            logger.info("🚀 Running in POLLING mode (lightweight checks)")
            logger.info(f"   - Check interval: {self.lightweight_check_interval}s")
            logger.info(f"   - Full query fallback: every {self.query_interval}s")

        # Запуск умного цикла опроса
        query_task = asyncio.create_task(self.smart_query_loop())

        # Запуск WebSocket сервера
        async with websockets.serve(
            self.handle_client,
            self.host,
            self.port,
            ping_interval=20,
            ping_timeout=10
        ) as server:
            logger.info(f"✓ WebSocket Server listening on {self.host}:{self.port}")
            logger.info(f"✓ Signal window: {self.signal_window_minutes} minutes")
            logger.info("=" * 70)

            try:
                await asyncio.Future()  # Работаем вечно
            except KeyboardInterrupt:
                logger.info("Shutting down server...")
            finally:
                self.running = False
                query_task.cancel()

                # Закрываем все соединения
                if self.connected_clients:
                    await asyncio.gather(
                        *[client.close() for client in self.connected_clients],
                        return_exceptions=True
                    )

                # Закрываем NOTIFY соединение
                if self.notify_connection:
                    try:
                        await self.notify_connection.close()
                        logger.info("NOTIFY connection closed")
                    except:
                        pass

                # Закрываем пул БД
                if self.db_pool:
                    await self.db_pool.close()

                logger.info("Server stopped")


def main():
    """Главная функция запуска"""
    import os
    from dotenv import load_dotenv

    # Загрузка конфигурации
    load_dotenv()

    config = {
        # WebSocket сервер
        'WS_SERVER_HOST': os.getenv('WS_SERVER_HOST', '0.0.0.0'),
        'WS_SERVER_PORT': os.getenv('WS_SERVER_PORT', '8765'),
        'WS_AUTH_TOKEN': hashlib.sha256(
            os.getenv('WS_AUTH_PASSWORD', 'change_me_please').encode()
        ).hexdigest(),

        # База данных
        'DB_HOST': os.getenv('DB_HOST', 'localhost'),
        'DB_PORT': os.getenv('DB_PORT', '5432'),
        'DB_NAME': os.getenv('DB_NAME'),
        'DB_USER': os.getenv('DB_USER'),
        'DB_PASSWORD': os.getenv('DB_PASSWORD'),

        # Параметры опроса
        'QUERY_INTERVAL_SECONDS': os.getenv('QUERY_INTERVAL_SECONDS', '30'),
        'SIGNAL_WINDOW_MINUTES': os.getenv('SIGNAL_WINDOW_MINUTES', '32'),

        # Гибридный режим
        'USE_NOTIFY': os.getenv('USE_NOTIFY', 'true'),
        'NOTIFY_CHANNEL': os.getenv('NOTIFY_CHANNEL', 'new_signals'),
        'LIGHTWEIGHT_CHECK_INTERVAL': os.getenv('LIGHTWEIGHT_CHECK_INTERVAL', '1'),
        'NOTIFY_FALLBACK_INTERVAL': os.getenv('NOTIFY_FALLBACK_INTERVAL', '60'),

        # Управление биржами
        'BINANCE_ENABLED': os.getenv('BINANCE_ENABLED', 'true'),
        'BYBIT_ENABLED': os.getenv('BYBIT_ENABLED', 'true')
    }

    # Создание и запуск сервера
    server = SignalWebSocketServer(config)

    # Обработка сигналов завершения
    def signal_handler(sig, frame):
        logger.info(f"Received signal {sig}, shutting down...")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        logger.info("Server stopped by user")
    except Exception as e:
        logger.error(f"Server crashed: {e}")
        raise


if __name__ == '__main__':
    main()
