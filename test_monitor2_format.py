#!/usr/bin/env python3
"""
Демонстрация нового формата вывода monitor2.py
Показывает как будут отображаться данные с 15 полями
"""

import json
from datetime import datetime

# Пример данных в новом формате (15 полей)
sample_signals = [
    {
        'id': 5247877,
        'pair_symbol': 'ZKCUSDT',
        'recommended_action': 'BUY',
        'score_week': 86.20,
        'score_month': 69.10,
        'timestamp': '2025-10-21T02:15:00+00:00',
        'created_at': '2025-10-21T02:33:02.231292+00:00',
        'trading_pair_id': 1013315,
        'exchange_id': 1,
        'score_week_filter': 62.0,
        'score_month_filter': 70.0,
        'max_trades_filter': 5,
        'stop_loss_filter': 4.0,
        'trailing_activation_filter': 2.0,
        'trailing_distance_filter': 0.5
    },
    {
        'id': 5247876,
        'pair_symbol': 'OPENUSDT',
        'recommended_action': 'BUY',
        'score_week': 86.20,
        'score_month': 69.10,
        'timestamp': '2025-10-21T02:15:00+00:00',
        'created_at': '2025-10-21T02:33:02.231292+00:00',
        'trading_pair_id': 1013314,
        'exchange_id': 1,
        'score_week_filter': 62.0,
        'score_month_filter': 70.0,
        'max_trades_filter': 5,
        'stop_loss_filter': 4.0,
        'trailing_activation_filter': 2.0,
        'trailing_distance_filter': 0.5
    },
    {
        'id': 5247875,
        'pair_symbol': 'BTCUSDT',
        'recommended_action': 'SELL',
        'score_week': 75.50,
        'score_month': 82.30,
        'timestamp': '2025-10-21T02:10:00+00:00',
        'created_at': '2025-10-21T02:28:15.445566+00:00',
        'trading_pair_id': 1000001,
        'exchange_id': 1,
        'score_week_filter': 62.0,
        'score_month_filter': 70.0,
        'max_trades_filter': 5,
        'stop_loss_filter': 4.0,
        'trailing_activation_filter': 2.0,
        'trailing_distance_filter': 0.5
    }
]

def demo_simple_format(signals):
    """Демонстрация простого табличного формата"""
    print(f"\n{'='*180}")
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Демонстрация нового формата (15 полей)")
    print(f"{'='*180}")

    # Table header - Part 1: Basic fields (9 fields)
    print("\n📊 ОСНОВНЫЕ ПОЛЯ (9 полей):")
    header1 = (
        f"{'#':<4} {'ID':<10} {'Symbol':<12} {'Action':<6} {'Week':<7} {'Month':<7} "
        f"{'Timestamp':<22} {'Created At':<22} {'Pair ID':<8} {'Exch':<5}"
    )
    print(header1)
    print('-' * 110)

    # Table rows - Part 1
    for i, signal in enumerate(signals, 1):
        row1 = (
            f"{i:<4} "
            f"{signal.get('id', 'N/A'):<10} "
            f"{signal.get('pair_symbol', 'N/A'):<12} "
            f"{signal.get('recommended_action', 'N/A'):<6} "
            f"{signal.get('score_week', 0):<7.2f} "
            f"{signal.get('score_month', 0):<7.2f} "
            f"{str(signal.get('timestamp', 'N/A'))[:21]:<22} "
            f"{str(signal.get('created_at', 'N/A'))[:21]:<22} "
            f"{signal.get('trading_pair_id', 'N/A'):<8} "
            f"{signal.get('exchange_id', 'N/A'):<5}"
        )
        print(row1)

    # Table header - Part 2: Backtest parameters (6 fields)
    print("\n⚙️  ПАРАМЕТРЫ ИЗ BACKTEST_SUMMARY (6 полей):")
    header2 = (
        f"{'#':<4} {'Symbol':<12} "
        f"{'Week Filter':<12} {'Month Filter':<13} {'Max Trades':<11} "
        f"{'Stop Loss %':<12} {'Trail Act %':<11} {'Trail Dist %':<13}"
    )
    print(header2)
    print('-' * 90)

    # Table rows - Part 2
    for i, signal in enumerate(signals, 1):
        row2 = (
            f"{i:<4} "
            f"{signal.get('pair_symbol', 'N/A'):<12} "
            f"{signal.get('score_week_filter', 'N/A'):<12} "
            f"{signal.get('score_month_filter', 'N/A'):<13} "
            f"{signal.get('max_trades_filter', 'N/A'):<11} "
            f"{signal.get('stop_loss_filter', 'N/A'):<12} "
            f"{signal.get('trailing_activation_filter', 'N/A'):<11} "
            f"{signal.get('trailing_distance_filter', 'N/A'):<13}"
        )
        print(row2)

    print('=' * 180 + '\n')


def demo_compact_format(signals):
    """Демонстрация компактного формата"""
    print("\n" + "="*130)
    print("КОМПАКТНЫЙ ФОРМАТ (одна строка на сигнал)")
    print("="*130 + "\n")

    for signal in signals:
        output = (
            f"[{datetime.now().strftime('%H:%M:%S')}] "
            f"ID:{signal.get('id')} "
            f"{signal.get('pair_symbol'):<10} "
            f"{signal.get('recommended_action'):<4} "
            f"W:{signal.get('score_week'):.1f} "
            f"M:{signal.get('score_month'):.1f} | "
            f"Filters[W≥{signal.get('score_week_filter')} "
            f"M≥{signal.get('score_month_filter')} "
            f"MT:{signal.get('max_trades_filter')} "
            f"SL:{signal.get('stop_loss_filter')}% "
            f"TA:{signal.get('trailing_activation_filter')}% "
            f"TD:{signal.get('trailing_distance_filter')}%]"
        )
        print(output)

    print()


def demo_json_format(signal):
    """Демонстрация JSON формата"""
    print("\n" + "="*80)
    print("JSON ФОРМАТ (для отладки)")
    print("="*80 + "\n")
    print(json.dumps(signal, indent=2, ensure_ascii=False))
    print()


def main():
    """Запуск демонстрации"""
    print("\n" + "="*80)
    print("ДЕМОНСТРАЦИЯ ФОРМАТОВ ВЫВОДА MONITOR2.PY")
    print("Обновленный формат: 15 полей (9 основных + 6 из backtest_summary)")
    print("="*80)

    # 1. Простой табличный формат
    demo_simple_format(sample_signals)

    # 2. Компактный формат
    demo_compact_format(sample_signals)

    # 3. JSON формат (первый сигнал)
    demo_json_format(sample_signals[0])

    # Сводка
    print("="*80)
    print("СВОДКА:")
    print(f"  Всего полей в сигнале: 15")
    print(f"  - Основные поля: 9")
    print(f"    (id, pair_symbol, recommended_action, score_week, score_month,")
    print(f"     timestamp, created_at, trading_pair_id, exchange_id)")
    print(f"  - Поля из backtest_summary: 6")
    print(f"    (score_week_filter, score_month_filter, max_trades_filter,")
    print(f"     stop_loss_filter, trailing_activation_filter, trailing_distance_filter)")
    print("="*80)
    print("\nИСПОЛЬЗОВАНИЕ MONITOR2.PY:")
    print("  # Простой режим (таблицы):")
    print("  python3 monitor2.py --url ws://localhost:8765 --token YOUR_TOKEN --mode simple")
    print("\n  # Компактный режим (одна строка):")
    print("  python3 monitor2.py --url ws://localhost:8765 --token YOUR_TOKEN --mode compact")
    print("\n  # Полный режим (TUI интерфейс):")
    print("  python3 monitor2.py --url ws://localhost:8765 --token YOUR_TOKEN --mode full")
    print("="*80 + "\n")


if __name__ == '__main__':
    main()
