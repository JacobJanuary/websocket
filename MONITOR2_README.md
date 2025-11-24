# Monitor2.py - Расширенный мониторинг WebSocket сервера

## Обзор

`monitor2.py` - обновленная версия монитора для Signal WebSocket Server с поддержкой **расширенного формата данных** (15 полей вместо 9).

### Что нового?

**Версия 1 (monitor.py):** 9 полей
**Версия 2 (monitor2.py):** 15 полей = 9 основных + 6 из `backtest_summary`

## Структура данных

### Основные поля (9 шт):
1. `id` - ID сигнала
2. `pair_symbol` - Торговая пара (например, BTCUSDT)
3. `recommended_action` - Рекомендуемое действие (BUY/SELL)
4. `score_week` - Недельный скор
5. `score_month` - Месячный скор
6. `timestamp` - Временная метка сигнала
7. `created_at` - Время создания записи
8. `trading_pair_id` - ID торговой пары
9. `exchange_id` - ID биржи

### Новые поля из backtest_summary (6 шт):
10. `score_week_filter` - Фильтр по недельному скору
11. `score_month_filter` - Фильтр по месячному скору
12. `max_trades_filter` - Максимальное количество сделок
13. `stop_loss_filter` - Стоп-лосс (%)
14. `trailing_activation_filter` - Активация трейлинга (%)
15. `trailing_distance_filter` - Дистанция трейлинга (%)

## Режимы работы

### 1. Simple Mode (простой режим)
Табличный вывод с двумя таблицами:
- Таблица 1: Основные 9 полей
- Таблица 2: Параметры из backtest_summary (6 полей)

```bash
python3 monitor2.py --url ws://localhost:8765 --token YOUR_TOKEN --mode simple
```

**Вывод:**
```
📊 ОСНОВНЫЕ ПОЛЯ:
#    ID         Symbol       Action Week    Month   Timestamp              ...
1    5247877    ZKCUSDT      BUY    86.20   69.10   2025-10-21T02:15:00   ...

⚙️  ПАРАМЕТРЫ ИЗ BACKTEST_SUMMARY:
#    Symbol       Week Filter  Month Filter  Max Trades  Stop Loss %  ...
1    ZKCUSDT      62.0         70.0          5           4.0          ...
```

### 2. Compact Mode (компактный режим)
Вся информация в одной строке на сигнал - идеально для логов.

```bash
python3 monitor2.py --url ws://localhost:8765 --token YOUR_TOKEN --mode compact
```

**Вывод:**
```
[03:00:14] ID:5247877 ZKCUSDT BUY W:86.2 M:69.1 | Filters[W≥62.0 M≥70.0 MT:5 SL:4.0% TA:2.0% TD:0.5%]
```

### 3. Full Mode (полный режим)
Интерактивный TUI интерфейс с curses - показывает статистику в реальном времени.

```bash
python3 monitor2.py --url ws://localhost:8765 --token YOUR_TOKEN --mode full
```

**Возможности:**
- Статистика подключения
- Скорость получения сигналов
- Последние 5 сигналов с параметрами
- Интерактивное управление (q - выход, r - запрос сигналов, s - статистика)

## Установка и настройка

### Требования
```bash
# Активировать виртуальное окружение
source venv/bin/activate

# Установить зависимости (уже установлены)
pip install -r requirements.txt
```

### Получение токена
Токен аутентификации находится в `.env` файле:
```bash
cat .env | grep WS_AUTH_PASSWORD
```

## Примеры использования

### Запуск с локальным сервером
```bash
# Simple mode
python3 monitor2.py --url ws://localhost:8765 --token "your_secret_token" --mode simple

# Compact mode (для логирования в файл)
python3 monitor2.py --url ws://localhost:8765 --token "your_secret_token" --mode compact >> monitor.log

# Full TUI mode
python3 monitor2.py --url ws://localhost:8765 --token "your_secret_token" --mode full
```

### Запуск с удаленным сервером
```bash
python3 monitor2.py --url ws://production-server:8765 --token "your_secret_token" --mode simple
```

## Сравнение с monitor.py

| Функция | monitor.py | monitor2.py |
|---------|-----------|-------------|
| Основных полей | 9 | 9 |
| Полей из backtest | 0 | 6 |
| Всего полей | 9 | **15** |
| Simple mode | ✅ | ✅ Улучшен |
| Full TUI mode | ✅ | ✅ Улучшен |
| Compact mode | ❌ | ✅ **Новый** |
| JSON debug view | ❌ | ✅ **Новый** |

## Тестирование

### Демонстрация форматов
```bash
python3 test_monitor2_format.py
```

Показывает примеры вывода всех трех режимов с тестовыми данными.

### Проверка импорта
```bash
source venv/bin/activate
python3 -c "from monitor2 import SimpleMonitor, SignalMonitor, CompactMonitor; print('OK')"
```

## Интеграция в производство

### Как systemd сервис
```bash
# Создать сервис для мониторинга
sudo nano /etc/systemd/system/signal-monitor.service
```

```ini
[Unit]
Description=Signal WebSocket Monitor
After=signal-websocket.service

[Service]
Type=simple
User=elcrypto
WorkingDirectory=/home/elcrypto/websocket
ExecStart=/home/elcrypto/websocket/venv/bin/python3 monitor2.py \
    --url ws://localhost:8765 \
    --token YOUR_TOKEN \
    --mode compact
Restart=always

[Install]
WantedBy=multi-user.target
```

### Запуск в tmux/screen
```bash
# В отдельной сессии
tmux new -s monitor
python3 monitor2.py --url ws://localhost:8765 --token YOUR_TOKEN --mode full
# Ctrl+B, D для отсоединения
```

## Устранение неполадок

### Проблема: "ModuleNotFoundError: No module named 'signal_websocket_client'"
**Решение:**
```bash
source venv/bin/activate
```

### Проблема: Не подключается к серверу
**Решение:**
```bash
# Проверить статус сервера
sudo systemctl status signal-websocket

# Проверить логи
tail -f signal_ws_server.log

# Проверить порт
netstat -tuln | grep 8765
```

### Проблема: "Authentication failed"
**Решение:**
```bash
# Проверить токен в .env
cat .env | grep WS_AUTH_PASSWORD

# Использовать правильный токен (не хеш!)
python3 monitor2.py --url ws://localhost:8765 --token "actual_password_not_hash" --mode simple
```

## Расширенные возможности

### Фильтрация вывода
```bash
# Только BUY сигналы
python3 monitor2.py --url ws://localhost:8765 --token TOKEN --mode compact | grep " BUY "

# Только определенная пара
python3 monitor2.py --url ws://localhost:8765 --token TOKEN --mode compact | grep "BTCUSDT"
```

### Сохранение в файл с ротацией
```bash
# С помощью logrotate
python3 monitor2.py --url ws://localhost:8765 --token TOKEN --mode compact >> /var/log/signals.log
```

## API для программного использования

```python
from monitor2 import SimpleMonitor
import asyncio

config = {
    'SIGNAL_WS_URL': 'ws://localhost:8765',
    'SIGNAL_WS_TOKEN': 'your_token',
    'AUTO_RECONNECT': True
}

# Создать монитор
monitor = SimpleMonitor(config)

# Запустить
asyncio.run(monitor.run())
```

## Производительность

- **Compact mode**: ~50 байт на сигнал в логах
- **Simple mode**: ~200 байт на сигнал
- **Full mode**: обновление экрана каждые 100мс
- **Память**: ~10-20 MB RAM
- **CPU**: < 1% при получении сигналов

## Лицензия

Часть проекта Signal WebSocket Server.

## Changelog

### v2.0 (2025-10-21)
- ✅ Добавлена поддержка 6 новых полей из `backtest_summary`
- ✅ Новый Compact Mode для однострочного вывода
- ✅ Улучшенный Simple Mode с двумя таблицами
- ✅ JSON debug view для отладки
- ✅ Обновлен TUI интерфейс для отображения параметров backtest

### v1.0
- Базовая версия с 9 полями

## Поддержка

При возникновении проблем:
1. Проверьте логи: `tail -f signal_ws_server.log`
2. Проверьте статус: `sudo systemctl status signal-websocket`
3. Запустите тест: `python3 test_monitor2_format.py`
