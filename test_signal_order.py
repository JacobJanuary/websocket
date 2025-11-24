#!/usr/bin/env python3
"""
Тест для проверки сортировки сигналов от сервера
"""
import asyncio
import json
import os
from dotenv import load_dotenv
import websockets

async def test_signal_order():
    """Проверяет порядок сигналов, получаемых от сервера"""
    load_dotenv()

    server_url = os.getenv('SIGNAL_WS_URL', 'ws://localhost:8765')
    auth_token = os.getenv('WS_AUTH_PASSWORD', 'secure_websocket_pass_2024')

    print(f"🔌 Подключаюсь к серверу: {server_url}")

    try:
        async with websockets.connect(server_url) as websocket:
            # Читаем auth_required
            auth_req = await websocket.recv()
            print(f"📩 Получен запрос: {json.loads(auth_req)['type']}")

            # Отправляем токен
            await websocket.send(json.dumps({
                'type': 'auth',
                'token': auth_token
            }))
            print(f"🔑 Токен отправлен")

            # Читаем ответ на аутентификацию
            auth_response = await websocket.recv()
            auth_data = json.loads(auth_response)

            if auth_data.get('type') == 'auth_success':
                print(f"✅ Аутентификация успешна")
            else:
                print(f"❌ Аутентификация не удалась: {auth_data}")
                return

            # Ждем сигналы или запрашиваем их
            print(f"\n🎯 Запрашиваю сигналы...")
            await websocket.send(json.dumps({
                'type': 'get_signals'
            }))

            # Читаем ответ
            signals_msg = await websocket.recv()
            signals_data = json.loads(signals_msg)

            if signals_data.get('type') == 'signals':
                signals = signals_data.get('data', [])
                count = signals_data.get('count', 0)

                print(f"\n📊 Получено {count} сигналов")
                print("=" * 80)

                if not signals:
                    print("⚠️  Сигналов нет!")
                    return

                # Проверяем сортировку
                print(f"\n{'№':<4} {'ID':<8} {'Symbol':<12} {'score_week':<12} {'score_month':<12} {'Action'}")
                print("-" * 80)

                prev_score = float('inf')
                is_sorted = True

                for i, signal in enumerate(signals, 1):
                    score_week = signal.get('score_week', 0)
                    score_month = signal.get('score_month', 0)
                    symbol = signal.get('pair_symbol', 'N/A')
                    action = signal.get('recommended_action', 'N/A')
                    sig_id = signal.get('id', 'N/A')

                    # Проверяем порядок
                    if score_week > prev_score:
                        is_sorted = False
                        marker = "❌"
                    else:
                        marker = "✅"

                    print(f"{marker} {i:<3} {sig_id:<8} {symbol:<12} {score_week:<12.2f} {score_month:<12.2f} {action}")
                    prev_score = score_week

                print("=" * 80)

                if is_sorted:
                    print("\n✅ СИГНАЛЫ ОТСОРТИРОВАНЫ ПРАВИЛЬНО (по убыванию score_week)")
                else:
                    print("\n❌ СИГНАЛЫ НЕ ОТСОРТИРОВАНЫ! Найдены нарушения порядка")

                # Дополнительная проверка
                scores = [s.get('score_week', 0) for s in signals]
                sorted_scores = sorted(scores, reverse=True)

                if scores == sorted_scores:
                    print("✅ Подтверждение: порядок соответствует сортировке DESC")
                else:
                    print("❌ Подтверждение: порядок НЕ соответствует сортировке DESC")
                    print(f"\nПолучено:  {scores[:10]}")
                    print(f"Ожидалось: {sorted_scores[:10]}")

            else:
                print(f"❌ Неожиданный тип сообщения: {signals_data.get('type')}")

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    asyncio.run(test_signal_order())
