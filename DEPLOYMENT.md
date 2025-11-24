# Инструкция по развертыванию WebSocket Signal Server

## Оглавление
1. [Требования](#требования)
2. [Подготовка сервера](#подготовка-сервера)
3. [Установка проекта](#установка-проекта)
4. [Настройка базы данных](#настройка-базы-данных)
5. [Настройка PostgreSQL триггера](#настройка-postgresql-триггера)
6. [Конфигурация сервера](#конфигурация-сервера)
7. [Запуск и тестирование](#запуск-и-тестирование)
8. [Установка как системный сервис](#установка-как-системный-сервис)
9. [Мониторинг и отладка](#мониторинг-и-отладка)
10. [Безопасность](#безопасность)

---

## Требования

### Системные требования
- **OS:** Ubuntu 20.04+ / Debian 11+ / CentOS 8+
- **Python:** 3.8+
- **PostgreSQL:** 12+
- **RAM:** минимум 512 MB (рекомендуется 1 GB)
- **Disk:** минимум 100 MB свободного места

### Сетевые требования
- Открытый порт для WebSocket (по умолчанию 8765)
- Доступ к PostgreSQL серверу (локально или удаленно)
- Если PostgreSQL на другом сервере, открыт порт 5432

---

## Подготовка сервера

### 1. Обновление системы

```bash
# Ubuntu/Debian
sudo apt update && sudo apt upgrade -y

# CentOS/RHEL
sudo yum update -y
```

### 2. Установка зависимостей

```bash
# Ubuntu/Debian
sudo apt install -y python3 python3-pip python3-venv postgresql-client git

# CentOS/RHEL
sudo yum install -y python3 python3-pip postgresql git
```

### 3. Создание пользователя для сервиса (опционально, рекомендуется)

```bash
# Создать пользователя без домашней директории
sudo useradd -r -s /bin/bash -d /opt/websocket websocket-server

# Создать директорию для проекта
sudo mkdir -p /opt/websocket
sudo chown websocket-server:websocket-server /opt/websocket
```

---

## Установка проекта

### 1. Распаковка архива

```bash
# Если используете специального пользователя
sudo -u websocket-server bash
cd /opt/websocket

# Или в вашей домашней директории
cd ~
mkdir websocket
cd websocket

# Распаковать архив
tar -xzf signal-websocket-server.tar.gz
cd signal-websocket-server
```

### 2. Запуск установки

```bash
# Скрипт установит все Python зависимости в venv
chmod +x install.sh
./install.sh
```

Скрипт выполнит:
- Создание виртуального окружения Python
- Установку всех необходимых пакетов
- Проверку зависимостей

---

## Настройка базы данных

### 1. Проверка доступа к PostgreSQL

```bash
# Тест подключения
psql -h DB_HOST -U DB_USER -d DB_NAME -c "SELECT version();"
```

Если подключение не работает:

**Для локального PostgreSQL:**
```bash
# Редактировать pg_hba.conf
sudo nano /etc/postgresql/*/main/pg_hba.conf

# Добавить строку (для локального доступа):
local   all   all   md5

# Перезапустить PostgreSQL
sudo systemctl restart postgresql
```

**Для удаленного PostgreSQL:**
```bash
# На сервере PostgreSQL отредактировать pg_hba.conf
# Добавить строку (замените IP_ADDRESS на IP вашего сервера):
host    all   all   IP_ADDRESS/32   md5

# Также в postgresql.conf:
listen_addresses = '*'

# Перезапустить PostgreSQL
sudo systemctl restart postgresql
```

### 2. Проверка схемы базы данных

```bash
# Подключиться к БД
psql -h DB_HOST -U DB_USER -d DB_NAME

-- Проверить наличие необходимых таблиц
\dt fas_v2.scoring_history
\dt public.trading_pairs

-- Проверить структуру scoring_history
\d fas_v2.scoring_history

-- Необходимые поля:
-- - id
-- - pair_symbol
-- - recommended_action
-- - score_week
-- - score_month
-- - timestamp
-- - created_at
-- - trading_pair_id
-- - is_active

-- Выход
\q
```

---

## Настройка PostgreSQL триггера

### 1. Проверка прав пользователя

```sql
-- Подключиться к БД
psql -h DB_HOST -U DB_USER -d DB_NAME

-- Проверить права на создание функций и триггеров
SELECT has_schema_privilege('fas', 'CREATE');
SELECT has_table_privilege('fas_v2.scoring_history', 'TRIGGER');
```

Если прав нет, выполните от суперпользователя:

```sql
-- От пользователя postgres
psql -U postgres -d DB_NAME

-- Выдать права
GRANT CREATE ON SCHEMA fas TO your_user;
GRANT TRIGGER ON fas_v2.scoring_history TO your_user;
```

### 2. Установка триггера

```bash
# Способ 1: Через psql
psql -h DB_HOST -U DB_USER -d DB_NAME -f setup_notify_trigger.sql

# Способ 2: Интерактивно
psql -h DB_HOST -U DB_USER -d DB_NAME
```

В psql:
```sql
-- Скопируйте и выполните содержимое setup_notify_trigger.sql
\i setup_notify_trigger.sql
```

### 3. Проверка триггера

```sql
-- Проверить что функция создана
SELECT proname, prosrc
FROM pg_proc
WHERE proname = 'notify_new_signal';

-- Проверить что триггер создан
SELECT tgname, tgtype, tgenabled
FROM pg_trigger
WHERE tgname = 'trigger_notify_new_signal';

-- Тест триггера (вставить тестовую запись)
INSERT INTO fas_v2.scoring_history (
    pair_symbol,
    recommended_action,
    score_week,
    score_month,
    timestamp,
    trading_pair_id,
    is_active
) VALUES (
    'TESTUSDT',
    'BUY',
    75.5,
    68.2,
    NOW(),
    1,
    true
);

-- Если триггер работает, вы должны увидеть NOTIFY в логах PostgreSQL
-- Удалить тестовую запись
DELETE FROM fas_v2.scoring_history WHERE pair_symbol = 'TESTUSDT';
```

### 4. Включение логирования NOTIFY (опционально, для отладки)

```sql
-- В postgresql.conf (требует перезапуска)
log_statement = 'all'

-- Или только для текущей сессии
SET log_statement = 'all';

-- Проверить логи
sudo tail -f /var/log/postgresql/postgresql-*-main.log
```

---

## Конфигурация сервера

### 1. Создание файла конфигурации

```bash
# Скопировать пример
cp .env.example .env

# Редактировать конфигурацию
nano .env
```

### 2. Обязательные параметры

```ini
# === DATABASE CONFIGURATION ===
DB_HOST=localhost              # IP или hostname PostgreSQL сервера
DB_PORT=5432                   # Порт PostgreSQL
DB_NAME=your_database_name     # Имя базы данных
DB_USER=your_database_user     # Пользователь БД
DB_PASSWORD=your_secure_pass   # Пароль БД

# === WEBSOCKET SERVER ===
WS_SERVER_HOST=0.0.0.0        # 0.0.0.0 = слушать все интерфейсы
WS_SERVER_PORT=8765           # Порт WebSocket сервера
WS_AUTH_PASSWORD=change_me_NOW_to_secure_password  # ВАЖНО: смените!

# === QUERY SETTINGS ===
QUERY_INTERVAL_SECONDS=30     # Интервал fallback проверки (секунды)
SIGNAL_WINDOW_MINUTES=32      # Окно выборки сигналов (минуты)

# === HYBRID MODE ===
USE_NOTIFY=true               # true = включить PostgreSQL NOTIFY (рекомендуется)
NOTIFY_CHANNEL=new_signals    # Имя канала NOTIFY
LIGHTWEIGHT_CHECK_INTERVAL=1  # Интервал легковесных проверок (секунды)
NOTIFY_FALLBACK_INTERVAL=60   # Интервал fallback при NOTIFY режиме (секунды)
```

### 3. Генерация безопасного пароля

```bash
# Сгенерировать случайный пароль
openssl rand -base64 32

# Или
python3 -c "import secrets; print(secrets.token_urlsafe(32))"

# Записать в .env
```

### 4. Защита конфигурации

```bash
# Установить права доступа только для владельца
chmod 600 .env

# Проверить
ls -la .env
# Должно быть: -rw------- (только владелец может читать/писать)
```

---

## Запуск и тестирование

### 1. Тестовый запуск сервера

```bash
# Активировать venv и запустить
./venv/bin/python3 signal_websocket_server.py
```

Ожидаемый вывод:
```
2025-10-08 12:00:00 - SignalWSServer - INFO - Signal WebSocket Server initialized on 0.0.0.0:8765
2025-10-08 12:00:00 - SignalWSServer - INFO - Database pool created successfully
2025-10-08 12:00:00 - SignalWSServer - INFO - ✓ PostgreSQL NOTIFY listener active on channel 'new_signals'
2025-10-08 12:00:00 - SignalWSServer - INFO - ✓ Initial signals loaded: XX signals
2025-10-08 12:00:00 - SignalWSServer - INFO - 🚀 Running in NOTIFY mode (event-driven)
2025-10-08 12:00:00 - SignalWSServer - INFO - ✓ WebSocket Server listening on 0.0.0.0:8765
```

### 2. Проверка портов

В другом терминале:
```bash
# Проверить что порт слушается
sudo netstat -tlnp | grep 8765
# Или
sudo ss -tlnp | grep 8765

# Ожидаемый результат:
# tcp  0  0  0.0.0.0:8765  0.0.0.0:*  LISTEN  12345/python3
```

### 3. Тест подключения клиента

```bash
# В другом терминале
./venv/bin/python3 test_signal_order.py
```

Ожидаемый вывод:
```
🔌 Подключаюсь к серверу: ws://localhost:8765
✅ Аутентификация успешна
📊 Получено XX сигналов
✅ СИГНАЛЫ ОТСОРТИРОВАНЫ ПРАВИЛЬНО
```

### 4. Тест сортировки

```bash
# Тест сервера
./venv/bin/python3 test_signal_order.py

# Тест клиента
./venv/bin/python3 test_client_order.py

# Тест NOTIFY режима
./venv/bin/python3 test_hybrid_mode.py
```

### 5. Мониторинг в реальном времени

```bash
# Простой вариант
./venv/bin/python3 monitor.py --url ws://localhost:8765 --token YOUR_PASSWORD --simple

# С таблицей
./venv/bin/python3 monitor.py --url ws://localhost:8765 --token YOUR_PASSWORD
```

### 6. Проверка файрвола

Если клиенты будут подключаться извне:

```bash
# Ubuntu/Debian (ufw)
sudo ufw allow 8765/tcp
sudo ufw status

# CentOS/RHEL (firewalld)
sudo firewall-cmd --permanent --add-port=8765/tcp
sudo firewall-cmd --reload
sudo firewall-cmd --list-ports
```

---

## Установка как системный сервис

### 1. Редактирование service файла

```bash
nano signal-websocket.service
```

**Обязательно исправьте пути:**
```ini
[Unit]
Description=WebSocket Signal Server
After=network.target postgresql.service

[Service]
Type=simple
User=websocket-server          # ← Ваш пользователь
WorkingDirectory=/opt/websocket # ← Путь к проекту
Environment="PATH=/opt/websocket/venv/bin"  # ← Путь к venv
ExecStart=/opt/websocket/venv/bin/python3 /opt/websocket/signal_websocket_server.py

Restart=always
RestartSec=10

# Безопасность
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

### 2. Установка сервиса

```bash
# Автоматическая установка
sudo ./install_service.sh

# ИЛИ вручную:
sudo cp signal-websocket.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable signal-websocket
sudo systemctl start signal-websocket
```

### 3. Проверка статуса

```bash
# Статус сервиса
sudo systemctl status signal-websocket

# Логи
sudo journalctl -u signal-websocket -f

# Или файловые логи
tail -f signal_ws_server.log
```

### 4. Управление сервисом

```bash
# Запуск
sudo systemctl start signal-websocket

# Остановка
sudo systemctl stop signal-websocket

# Перезапуск
sudo systemctl restart signal-websocket

# Автозапуск
sudo systemctl enable signal-websocket

# Отключить автозапуск
sudo systemctl disable signal-websocket
```

---

## Мониторинг и отладка

### 1. Проверка логов

```bash
# Системные логи
sudo journalctl -u signal-websocket -n 100

# Логи в реальном времени
sudo journalctl -u signal-websocket -f

# Логи приложения
tail -f /opt/websocket/signal_ws_server.log

# Последние 100 строк
tail -n 100 /opt/websocket/signal_ws_server.log
```

### 2. Проверка подключений

```bash
# Активные подключения к порту
sudo netstat -anp | grep 8765

# Количество подключений
sudo netstat -an | grep 8765 | grep ESTABLISHED | wc -l
```

### 3. Проверка производительности

```bash
# Использование CPU и памяти
ps aux | grep signal_websocket_server

# Детальная информация
top -p $(pgrep -f signal_websocket_server)
```

### 4. Тест NOTIFY триггера

```sql
-- В PostgreSQL вставить тестовый сигнал
INSERT INTO fas_v2.scoring_history (
    pair_symbol, recommended_action,
    score_week, score_month, timestamp,
    trading_pair_id, is_active
) VALUES (
    'TESTUSDT', 'BUY',
    75.0, 65.0, NOW(),
    1, true
);

-- В логах сервера должна появиться запись:
-- "⚡ NOTIFY received: event=INSERT, symbol=TESTUSDT, score=75.0"

-- Удалить тест
DELETE FROM fas_v2.scoring_history WHERE pair_symbol = 'TESTUSDT';
```

### 5. Типичные проблемы

| Проблема | Причина | Решение |
|----------|---------|---------|
| Порт уже используется | Другое приложение на порту 8765 | `sudo lsof -i :8765` → остановить приложение или сменить порт |
| Ошибка подключения к БД | Неверные credentials или firewall | Проверить .env, pg_hba.conf, firewall |
| NOTIFY не работает | Триггер не установлен | Повторить установку триггера |
| Authentication failed | Неверный WS_AUTH_PASSWORD | Проверить .env на сервере и токен у клиента |
| No signals received | Нет данных в БД или is_active=false | Проверить SELECT из БД |

---

## Безопасность

### 1. Базовая защита

```bash
# 1. Файрвол - разрешить только известные IP
sudo ufw allow from TRUSTED_IP to any port 8765

# 2. Fail2ban для защиты от брутфорса (опционально)
sudo apt install fail2ban

# Создать фильтр /etc/fail2ban/filter.d/websocket.conf:
[Definition]
failregex = Authentication failed for <HOST>
ignoreregex =

# Создать jail /etc/fail2ban/jail.d/websocket.conf:
[websocket]
enabled = true
port = 8765
logpath = /opt/websocket/signal_ws_server.log
maxretry = 5
bantime = 3600
```

### 2. SSL/TLS (опционально, рекомендуется для production)

Для WSS (WebSocket Secure) используйте nginx как reverse proxy:

```bash
# Установить nginx
sudo apt install nginx

# Конфигурация /etc/nginx/sites-available/websocket
upstream websocket {
    server 127.0.0.1:8765;
}

server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    location / {
        proxy_pass http://websocket;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}

# Активировать
sudo ln -s /etc/nginx/sites-available/websocket /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 3. Ротация логов

```bash
# Создать /etc/logrotate.d/signal-websocket
/opt/websocket/*.log {
    daily
    rotate 7
    compress
    delaycompress
    missingok
    notifempty
    create 644 websocket-server websocket-server
}

# Тест
sudo logrotate -d /etc/logrotate.d/signal-websocket
```

### 4. Регулярные обновления

```bash
# Обновление зависимостей
cd /opt/websocket
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt --upgrade

# Перезапуск сервиса
sudo systemctl restart signal-websocket
```

---

## Checklist развертывания

- [ ] Сервер обновлен и подготовлен
- [ ] Python 3.8+ установлен
- [ ] PostgreSQL клиент установлен
- [ ] Проект распакован и install.sh выполнен
- [ ] Доступ к PostgreSQL проверен
- [ ] Схема БД проверена (fas_v2.scoring_history, trading_pairs)
- [ ] PostgreSQL триггер установлен и протестирован
- [ ] .env файл создан и настроен
- [ ] WS_AUTH_PASSWORD изменен на безопасный
- [ ] Права на .env установлены (600)
- [ ] Тестовый запуск сервера успешен
- [ ] Порт 8765 открыт в файрволе
- [ ] Тесты пройдены (test_signal_order.py, test_client_order.py)
- [ ] Systemd сервис установлен
- [ ] Сервис запущен и работает
- [ ] Автозапуск включен
- [ ] Логи проверены
- [ ] Мониторинг настроен

---

## Полезные команды

```bash
# Статус всего стека
sudo systemctl status postgresql signal-websocket

# Перезапуск всего стека
sudo systemctl restart postgresql signal-websocket

# Проверка конфигурации
cat .env | grep -v '^#' | grep -v '^$'

# Быстрый тест подключения
curl -i -N -H "Connection: Upgrade" \
     -H "Upgrade: websocket" \
     -H "Sec-WebSocket-Version: 13" \
     -H "Sec-WebSocket-Key: test" \
     http://localhost:8765/

# Очистка старых логов
find . -name "*.log" -mtime +7 -delete
```

---

## Контакты и поддержка

Для вопросов и проблем см. `README.md` и отчеты:
- `SORTING_FIX_REPORT.md` - информация о сортировке сигналов
- `CLEANUP_REPORT.md` - структура проекта

---

**Дата создания:** 2025-10-08
**Версия:** 1.0
