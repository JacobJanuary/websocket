# WebSocket Signal Server

Real-time trading signals WebSocket server with PostgreSQL NOTIFY support.

## Features

- **Real-time signals** with < 10ms latency via PostgreSQL NOTIFY
- **Automatic fallback** to polling mode if NOTIFY unavailable
- **Token authentication** for secure access
- **8 essential fields** per signal (optimized)

## Quick Start

### 1. Installation

```bash
./install.sh
```

### 2. Database Setup

Install PostgreSQL trigger for real-time NOTIFY:

```bash
psql -U your_user -d your_database -f setup_notify_trigger.sql
```

### 3. Start Server

```bash
./venv/bin/python3 signal_websocket_server.py
```

## Configuration

Edit `.env` file:

```ini
# Database
DB_HOST=localhost
DB_PORT=5432
DB_NAME=your_database
DB_USER=your_user
DB_PASSWORD=your_password

# WebSocket Server
WS_SERVER_HOST=0.0.0.0
WS_SERVER_PORT=8765
WS_AUTH_PASSWORD=your_secure_password

# Hybrid Mode (NOTIFY + Polling)
USE_NOTIFY=true
QUERY_INTERVAL_SECONDS=30
SIGNAL_WINDOW_MINUTES=32
```

## Testing

### Test signal sorting:
```bash
# Test server-side sorting
./venv/bin/python3 test_signal_order.py

# Test client-side sorting
./venv/bin/python3 test_client_order.py
```

### Test hybrid mode (NOTIFY):
```bash
./venv/bin/python3 test_hybrid_mode.py
```

### Monitor signals in real-time:
```bash
./venv/bin/python3 monitor.py --url ws://localhost:8765 --token YOUR_PASSWORD --simple
```

## Project Structure

```
websocket/
├── signal_websocket_server.py    # WebSocket сервер
├── signal_websocket_client.py    # WebSocket клиент
├── monitor.py                    # Мониторинг сигналов
│
├── test_signal_order.py          # Тест сортировки (сервер)
├── test_client_order.py          # Тест сортировки (клиент)
├── test_hybrid_mode.py           # Тест NOTIFY режима
│
├── install.sh                    # Установка проекта
├── install_service.sh            # Установка systemd service
├── setup_notify_trigger.sql      # SQL триггер для NOTIFY
├── signal-websocket.service      # Systemd unit
│
├── requirements.txt              # Python зависимости
├── README.md                     # Документация
├── SORTING_FIX_REPORT.md         # Отчет об исправлении сортировки
└── .env                          # Конфигурация (создать из .env.example)
```

## Signal Format

Each signal contains 8 fields:

```json
{
  "id": 12345,
  "pair_symbol": "BTCUSDT",
  "recommended_action": "BUY",
  "score_week": 75.5,
  "score_month": 68.2,
  "timestamp": "2025-10-06T14:20:00",
  "created_at": "2025-10-06T14:20:05",
  "trading_pair_id": 1234
}
```

## Architecture

### NOTIFY Mode (Event-driven)
1. PostgreSQL trigger fires on INSERT/UPDATE
2. NOTIFY event sent to server (< 1ms)
3. Server queries updated signals
4. Broadcast to all connected clients (< 10ms total)

### Polling Mode (Fallback)
1. Lightweight check every 1 second (MAX(id), MAX(timestamp))
2. Full query only if changes detected
3. Broadcast to connected clients

## Production Deployment

For production deployment on another server:

1. Copy all files to production server
2. Edit `.env` with production credentials
3. Run `./install.sh`
4. Install PostgreSQL trigger: `psql -U user -d db -f setup_notify_trigger.sql`
5. Install as systemd service: `./install_service.sh`
6. Start service: `sudo systemctl start signal-websocket`

## Support

This is a test server. After complete testing, deploy to production.
