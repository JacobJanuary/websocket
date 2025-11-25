# High-Score Signal Server - Systemd Service Setup

## Файлы для настройки systemd сервиса

### 1. `high-score-signal-websocket.service`
Файл конфигурации systemd сервиса для high-score signal server.

**Основные параметры:**
- Порт: 25370
- Автозапуск при старте системы
- Автоматический перезапуск при сбоях
- Логи: `/home/elcrypto/websocket/logs/high_score_server.log`

### 2. `install_high_score_service.sh`
Скрипт автоматической установки и настройки сервиса.

## Быстрая установка

### Шаг 1: Установите сервис

```bash
sudo ./install_high_score_service.sh
```

Скрипт автоматически:
- ✅ Создаст директорию для логов
- ✅ Остановит запущенные процессы (если есть)
- ✅ Настроит пути и пользователя в service файле
- ✅ Установит systemd сервис
- ✅ Запустит сервис
- ✅ Проверит работоспособность (WebSocket на порту 25370)

### Шаг 2: Проверьте статус

```bash
sudo systemctl status high-score-signal-websocket
```

## Управление сервисом

### Основные команды

```bash
# Запустить
sudo systemctl start high-score-signal-websocket

# Остановить
sudo systemctl stop high-score-signal-websocket

# Перезапустить
sudo systemctl restart high-score-signal-websocket

# Проверить статус
sudo systemctl status high-score-signal-websocket

# Включить автозапуск
sudo systemctl enable high-score-signal-websocket

# Отключить автозапуск
sudo systemctl disable high-score-signal-websocket
```

## Просмотр логов

### Системные логи (journalctl)

```bash
# Последние 50 строк
sudo journalctl -u high-score-signal-websocket -n 50

# В реальном времени
sudo journalctl -u high-score-signal-websocket -f

# За последний час
sudo journalctl -u high-score-signal-websocket --since "1 hour ago"

# Только ошибки
sudo journalctl -u high-score-signal-websocket -p err
```

### Логи приложения

```bash
# Логи сервера
tail -f ~/websocket/logs/high_score_server.log

# Логи ошибок
tail -f ~/websocket/logs/high_score_error.log

# Последние 100 строк
tail -n 100 ~/websocket/logs/high_score_server.log
```

## Troubleshooting

### Сервис не запускается

```bash
# Проверьте логи
sudo journalctl -u high-score-signal-websocket -n 50

# Проверьте конфигурацию
sudo systemctl cat high-score-signal-websocket

# Перезагрузите systemd
sudo systemctl daemon-reload
sudo systemctl restart high-score-signal-websocket
```

### Порт уже занят

```bash
# Найдите процесс на порту 25370
sudo lsof -i :25370

# Или
sudo netstat -tulpn | grep 25370

# Завершите процесс
sudo kill <PID>
```

### База данных недоступна

```bash
# Проверьте PostgreSQL
sudo systemctl status postgresql

# Проверьте .env файл
cat .env | grep DB_

# Тестовое подключение
psql -h localhost -U your_user -d your_database -c "SELECT 1"
```

## Мониторинг в реальном времени

### Мониторинг логов с фильтром по ключевым событиям

```bash
# Broadcast сообщения (новые сигналы)
tail -f ~/websocket/logs/high_score_server.log | grep "📡 Broadcast"

# Ошибки
tail -f ~/websocket/logs/high_score_server.log | grep "ERROR"

# Подключения клиентов
tail -f ~/websocket/logs/high_score_server.log | grep "Client"

# NOTIFY события (event-driven mode)
tail -f ~/websocket/logs/high_score_server.log | grep "⚡ NOTIFY"
```

### Проверка доступности WebSocket

```bash
# Простой тест
echo '{"type":"ping"}' | websocat ws://localhost:25370

# Или через Python
python3 -c "
import asyncio
import websockets

async def test():
    async with websockets.connect('ws://localhost:25370') as ws:
        msg = await ws.recv()
        print('Server is responding:', msg)

asyncio.run(test())
"
```

## Запуск обоих серверов одновременно

```bash
# Установить оба сервиса
sudo ./install_service.sh                    # Стандартный сервер (порт 8765)
sudo ./install_high_score_service.sh         # High-Score сервер (порт 25370)

# Проверить статус обоих
sudo systemctl status signal-websocket
sudo systemctl status high-score-signal-websocket

# Посмотреть логи обоих в реальном времени (в двух терминалах)
# Терминал 1:
sudo journalctl -u signal-websocket -f

# Терминал 2:
sudo journalctl -u high-score-signal-websocket -f
```

## Деинсталляция

```bash
# Остановить и отключить сервис
sudo systemctl stop high-score-signal-websocket
sudo systemctl disable high-score-signal-websocket

# Удалить service файл
sudo rm /etc/systemd/system/high-score-signal-websocket.service

# Перезагрузить systemd
sudo systemctl daemon-reload

# Удалить логи (опционально)
rm -rf ~/websocket/logs/high_score_*
```

## Автоматический рестарт при обновлении кода

Если вы обновили `high_score_signal_server.py`:

```bash
# Просто перезапустите сервис
sudo systemctl restart high-score-signal-websocket

# Проверьте что все работает
sudo systemctl status high-score-signal-websocket
```

## Production чеклист

- [x] ✅ Systemd сервис настроен
- [x] ✅ Автозапуск при старте системы
- [x] ✅ Автоматический перезапуск при сбоях
- [x] ✅ Логирование в файлы
- [ ] Настроить logrotate для ротации логов
- [ ] Настроить мониторинг (Prometheus/Grafana)
- [ ] Настроить алерты на ошибки
- [ ] Добавить SSL/TLS (wss://)
- [ ] Настроить firewall правила
- [ ] Настроить backup логов

## Дополнительно

### Ротация логов (logrotate)

Создайте `/etc/logrotate.d/high-score-signal-websocket`:

```
/home/elcrypto/websocket/logs/high_score_*.log {
    daily
    rotate 14
    compress
    delaycompress
    notifempty
    missingok
    copytruncate
}
```

### Мониторинг CPU и памяти

```bash
# Использование ресурсов сервисом
systemd-cgtop -1 | grep high-score

# Или через ps
ps aux | grep high_score_signal_server.py
```

---

**Готово!** High-Score Signal Server настроен как systemd сервис и готов к production использованию! 🚀
