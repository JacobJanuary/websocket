#!/usr/bin/env python3
"""
Тест нового SQL запроса с параметрами из backtest_summary
"""

import asyncio
import asyncpg
import json
from dotenv import load_dotenv
import os

async def test_query():
    """Тестирование обновленного SQL запроса"""
    load_dotenv()

    # Подключение к БД
    conn = await asyncpg.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        port=int(os.getenv('DB_PORT', 5432)),
        database=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD')
    )

    print("=" * 80)
    print("Тестирование нового SQL запроса с backtest_summary параметрами")
    print("=" * 80)

    # SQL запрос (тот же что в сервере)
    query = """
        WITH best_params AS (
            SELECT
                score_week_filter,
                score_month_filter,
                max_trades_filter,
                stop_loss_filter,
                trailing_activation_filter,
                trailing_distance_filter
            FROM web.backtest_summary
            WHERE summary_id IN (
                SELECT summary_id
                FROM web.backtest_summary
                ORDER BY final_equity DESC
                LIMIT 5
            )
            ORDER BY win_rate DESC
            LIMIT 1
        )
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
            bp.score_week_filter,
            bp.score_month_filter,
            bp.max_trades_filter,
            bp.stop_loss_filter,
            bp.trailing_activation_filter,
            bp.trailing_distance_filter
        FROM fas_v2.scoring_history AS sc
        JOIN public.trading_pairs AS tp ON sc.trading_pair_id = tp.id
        CROSS JOIN best_params AS bp
        WHERE sc.timestamp >= now() - INTERVAL '32 minutes'
            AND sc.is_active = true
            AND tp.is_active = true
            AND sc.score_week > 50
            AND sc.score_month > 50
        ORDER BY sc.score_week DESC NULLS LAST, sc.timestamp DESC
        LIMIT 5
    """

    try:
        # Выполнение запроса
        print("\n📊 Выполнение запроса...\n")
        rows = await conn.fetch(query)

        print(f"✅ Получено сигналов: {len(rows)}\n")

        # Вывод первых 2 сигналов для проверки
        for i, row in enumerate(rows[:2], 1):
            print(f"Сигнал #{i}:")
            print(f"  ID: {row['id']}")
            print(f"  Пара: {row['pair_symbol']}")
            print(f"  Действие: {row['recommended_action']}")
            print(f"  Score Week: {row['score_week']}")
            print(f"  Score Month: {row['score_month']}")
            print(f"  Exchange ID: {row['exchange_id']}")
            print(f"  Timestamp: {row['timestamp']}")
            print(f"\n  Параметры из backtest_summary:")
            print(f"    score_week_filter: {row['score_week_filter']}")
            print(f"    score_month_filter: {row['score_month_filter']}")
            print(f"    max_trades_filter: {row['max_trades_filter']}")
            print(f"    stop_loss_filter: {row['stop_loss_filter']}")
            print(f"    trailing_activation_filter: {row['trailing_activation_filter']}")
            print(f"    trailing_distance_filter: {row['trailing_distance_filter']}")
            print()

        # Проверка структуры данных
        if rows:
            signal = {
                'id': rows[0]['id'],
                'pair_symbol': rows[0]['pair_symbol'],
                'recommended_action': rows[0]['recommended_action'],
                'score_week': float(rows[0]['score_week']) if rows[0]['score_week'] else 0,
                'score_month': float(rows[0]['score_month']) if rows[0]['score_month'] else 0,
                'timestamp': rows[0]['timestamp'].isoformat() if rows[0]['timestamp'] else None,
                'created_at': rows[0]['created_at'].isoformat() if rows[0]['created_at'] else None,
                'trading_pair_id': rows[0]['trading_pair_id'],
                'exchange_id': rows[0]['exchange_id'],
                'score_week_filter': float(rows[0]['score_week_filter']) if rows[0]['score_week_filter'] else None,
                'score_month_filter': float(rows[0]['score_month_filter']) if rows[0]['score_month_filter'] else None,
                'max_trades_filter': int(rows[0]['max_trades_filter']) if rows[0]['max_trades_filter'] else None,
                'stop_loss_filter': float(rows[0]['stop_loss_filter']) if rows[0]['stop_loss_filter'] else None,
                'trailing_activation_filter': float(rows[0]['trailing_activation_filter']) if rows[0]['trailing_activation_filter'] else None,
                'trailing_distance_filter': float(rows[0]['trailing_distance_filter']) if rows[0]['trailing_distance_filter'] else None
            }

            print("\n📦 JSON структура сигнала:")
            print(json.dumps(signal, indent=2, ensure_ascii=False))

            print(f"\n✅ Всего полей в ответе: {len(signal)}")
            print(f"   - Основных полей: 9")
            print(f"   - Полей из backtest_summary: 6")

        print("\n" + "=" * 80)
        print("✅ ТЕСТ УСПЕШНО ЗАВЕРШЕН!")
        print("=" * 80)

    except Exception as e:
        print(f"\n❌ ОШИБКА: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await conn.close()

if __name__ == '__main__':
    asyncio.run(test_query())
