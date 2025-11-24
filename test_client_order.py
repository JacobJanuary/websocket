#!/usr/bin/env python3
"""
Тест для проверки сохранения сортировки в клиенте
"""
import asyncio
import json
import os
import logging
from dotenv import load_dotenv
from signal_websocket_client import SignalWebSocketClient

logging.basicConfig(level=logging.INFO)

async def test_client_order():
    """Проверяет, сохраняет ли клиент сортировку сигналов"""
    load_dotenv()

    config = {
        'SIGNAL_WS_URL': os.getenv('SIGNAL_WS_URL', 'ws://localhost:8765'),
        'SIGNAL_WS_TOKEN': os.getenv('WS_AUTH_PASSWORD', 'secure_websocket_pass_2024'),
        'AUTO_RECONNECT': False,
        'SIGNAL_BUFFER_SIZE': 100
    }

    client = SignalWebSocketClient(config)
    signals_received = []

    async def on_signals(signals):
        """Callback для получения сигналов"""
        signals_received.append(signals)
        print(f"\n✅ Получено {len(signals)} сигналов через callback")

        # Проверяем сортировку
        print(f"\n{'№':<4} {'ID':<8} {'Symbol':<12} {'score_week':<12} {'Action'}")
        print("-" * 60)

        prev_score = float('inf')
        is_sorted = True

        for i, signal in enumerate(signals[:10], 1):  # Показываем топ-10
            score_week = signal.get('score_week', 0)
            symbol = signal.get('pair_symbol', 'N/A')
            action = signal.get('recommended_action', 'N/A')
            sig_id = signal.get('id', 'N/A')

            if score_week > prev_score:
                is_sorted = False
                marker = "❌"
            else:
                marker = "✅"

            print(f"{marker} {i:<3} {sig_id:<8} {symbol:<12} {score_week:<12.2f} {action}")
            prev_score = score_week

        print("-" * 60)

        if is_sorted:
            print("✅ Сигналы в callback отсортированы правильно")
        else:
            print("❌ Сигналы в callback НЕ отсортированы!")

        # Проверяем буфер
        print(f"\n📦 Проверка буфера клиента:")
        buffer = client.signal_buffer
        print(f"   Размер буфера: {len(buffer)}")

        if buffer:
            buffer_scores = [s.get('score_week', 0) for s in buffer[:5]]
            print(f"   Топ-5 score_week в буфере: {buffer_scores}")

            buffer_sorted = all(buffer[i].get('score_week', 0) >= buffer[i+1].get('score_week', 0)
                              for i in range(min(len(buffer)-1, 10)))

            if buffer_sorted:
                print("   ✅ Буфер отсортирован правильно")
            else:
                print("   ❌ Буфер НЕ отсортирован!")

    client.set_callbacks(on_signals=on_signals)

    print("🔌 Подключаюсь к серверу...")

    try:
        # Подключаемся
        success = await client.connect()

        if not success:
            print("❌ Не удалось подключиться")
            return

        print("✅ Подключение успешно")

        # Запрашиваем сигналы
        print("🎯 Запрашиваю сигналы...")
        await client.request_signals()

        # Ждем получения сигналов
        print("⏳ Жду сигналы...")
        for i in range(10):
            await asyncio.sleep(0.5)
            if signals_received:
                break

        if not signals_received:
            print("⚠️  Сигналы не получены!")
            # Попробуем прочитать сообщение вручную
            try:
                message = await asyncio.wait_for(client.websocket.recv(), timeout=2)
                print(f"📨 Получено сообщение: {message[:200]}")
                await client.handle_message(message)
            except asyncio.TimeoutError:
                print("⏱️  Таймаут при ожидании сообщения")

        # Закрываем соединение
        await client.stop()

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(test_client_order())
