#!/usr/bin/env python3
"""
Test script for Hybrid Mode functionality
Tests both NOTIFY and Polling modes
"""

import asyncio
import asyncpg
import os
from dotenv import load_dotenv
from datetime import datetime
import time

# Colors
GREEN = '\033[92m'
RED = '\033[91m'
YELLOW = '\033[93m'
BLUE = '\033[94m'
ENDC = '\033[0m'
BOLD = '\033[1m'


async def test_notify_trigger():
    """Test PostgreSQL NOTIFY trigger"""
    load_dotenv()

    print(f"{BLUE}{'='*70}{ENDC}")
    print(f"{BOLD}Testing PostgreSQL NOTIFY Trigger{ENDC}")
    print(f"{BLUE}{'='*70}{ENDC}\n")

    # Connect to database
    conn = await asyncpg.connect(
        host=os.getenv('DB_HOST'),
        port=int(os.getenv('DB_PORT', 5432)),
        database=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD')
    )

    print(f"{GREEN}✓{ENDC} Connected to database\n")

    # Check if triggers exist
    print("Checking triggers...")
    triggers = await conn.fetch("""
        SELECT trigger_name, event_manipulation
        FROM information_schema.triggers
        WHERE trigger_name LIKE 'trigger_notify%'
        ORDER BY trigger_name
    """)

    if not triggers:
        print(f"{RED}✗ No triggers found!{ENDC}")
        print(f"  Run: {YELLOW}./install_trigger.sh{ENDC}")
        await conn.close()
        return False

    print(f"{GREEN}✓{ENDC} Found {len(triggers)} trigger(s):")
    for trigger in triggers:
        print(f"  • {trigger['trigger_name']} ({trigger['event_manipulation']})")

    # Check if function exists
    print("\nChecking function...")
    func = await conn.fetchval("""
        SELECT COUNT(*)
        FROM pg_proc
        WHERE proname = 'notify_new_signals'
    """)

    if func > 0:
        print(f"{GREEN}✓{ENDC} Function notify_new_signals() exists")
    else:
        print(f"{RED}✗ Function not found!{ENDC}")
        await conn.close()
        return False

    # Test NOTIFY listener
    print(f"\n{BOLD}Testing NOTIFY listener...{ENDC}")

    notifications_received = []

    def notification_callback(connection, pid, channel, payload):
        notifications_received.append({
            'channel': channel,
            'payload': payload,
            'time': datetime.now()
        })
        print(f"{GREEN}⚡ NOTIFY received!{ENDC}")
        print(f"   Channel: {channel}")
        print(f"   Payload: {payload[:100]}")

    # Subscribe to channel
    channel = os.getenv('NOTIFY_CHANNEL', 'new_signals')
    await conn.add_listener(channel, notification_callback)
    print(f"Listening on channel '{channel}'...\n")

    # Insert test signal
    print(f"Inserting test signal...")
    start_time = time.time()

    try:
        test_id = await conn.fetchval("""
            INSERT INTO fas_v2.scoring_history (
                trading_pair_id,
                pair_symbol,
                timestamp,
                score_week,
                score_month,
                total_score,
                is_active,
                recommended_action
            ) VALUES (
                1,
                'TEST_HYBRID_USDT',
                NOW(),
                75.5,
                80.2,
                77.0,
                true,
                'BUY'
            ) RETURNING id
        """)

        print(f"{GREEN}✓{ENDC} Test signal inserted (ID: {test_id})")

        # Wait for NOTIFY (max 2 seconds)
        await asyncio.sleep(2)

        end_time = time.time()
        latency = (end_time - start_time) * 1000  # milliseconds

        if notifications_received:
            print(f"\n{GREEN}{BOLD}✓ NOTIFY TEST PASSED!{ENDC}")
            print(f"  Latency: {latency:.1f}ms")
            print(f"  Notifications received: {len(notifications_received)}")
        else:
            print(f"\n{YELLOW}⚠ No NOTIFY received{ENDC}")
            print("  Possible reasons:")
            print("  - Signal doesn't meet criteria (check score_week, score_month)")
            print("  - trading_pair_id=1 doesn't exist or not active")
            print("  - Trigger not working properly")

        # Cleanup
        await conn.execute(
            "DELETE FROM fas_v2.scoring_history WHERE id = $1",
            test_id
        )
        print(f"\n{GREEN}✓{ENDC} Test signal cleaned up")

    except Exception as e:
        print(f"\n{RED}✗ Error during test: {e}{ENDC}")
        return False

    finally:
        await conn.remove_listener(channel, notification_callback)
        await conn.close()

    return len(notifications_received) > 0


async def test_lightweight_check():
    """Test lightweight check query performance"""
    load_dotenv()

    print(f"\n{BLUE}{'='*70}{ENDC}")
    print(f"{BOLD}Testing Lightweight Check Performance{ENDC}")
    print(f"{BLUE}{'='*70}{ENDC}\n")

    conn = await asyncpg.connect(
        host=os.getenv('DB_HOST'),
        port=int(os.getenv('DB_PORT', 5432)),
        database=os.getenv('DB_NAME'),
        user=os.getenv('DB_USER'),
        password=os.getenv('DB_PASSWORD')
    )

    signal_window = int(os.getenv('SIGNAL_WINDOW_MINUTES', 32))

    # Test lightweight query
    print("Running lightweight query (MAX aggregates)...")
    start = time.time()

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
    """ % signal_window)

    lightweight_time = (time.time() - start) * 1000

    print(f"{GREEN}✓{ENDC} Lightweight query completed")
    print(f"  Time: {lightweight_time:.2f}ms")
    print(f"  Max ID: {result['max_id']}")
    print(f"  Count: {result['total_count']}")

    # Test full query for comparison
    print("\nRunning full query (all columns)...")
    start = time.time()

    signals = await conn.fetch("""
        SELECT
            sc.id,
            sc.timestamp,
            sc.pair_symbol,
            sc.trading_pair_id,
            sc.total_score,
            sc.pattern_score,
            sc.combination_score,
            sc.indicator_score,
            sc.score_week,
            sc.score_month,
            sc.recommended_action,
            sc.patterns_details,
            sc.combinations_details,
            tp.last_24h_volume,
            tp.exchange_id
        FROM fas_v2.scoring_history as sc
        JOIN public.trading_pairs as tp ON sc.trading_pair_id = tp.id
        WHERE sc.timestamp >= now() - INTERVAL '%s minutes'
            AND sc.is_active = true
            AND tp.is_active = true
            AND sc.score_week > 50
            AND sc.score_month > 50
        ORDER BY sc.score_week DESC NULLS LAST, sc.timestamp DESC
    """ % signal_window)

    full_time = (time.time() - start) * 1000

    print(f"{GREEN}✓{ENDC} Full query completed")
    print(f"  Time: {full_time:.2f}ms")
    print(f"  Rows: {len(signals)}")

    # Calculate improvement
    improvement = ((full_time - lightweight_time) / full_time) * 100
    speedup = full_time / lightweight_time if lightweight_time > 0 else 0

    print(f"\n{BOLD}Performance Summary:{ENDC}")
    print(f"  Lightweight query: {lightweight_time:.2f}ms")
    print(f"  Full query:        {full_time:.2f}ms")
    print(f"  {GREEN}Improvement:       {improvement:.1f}% faster ({speedup:.1f}x speedup){ENDC}")

    await conn.close()

    return True


async def main():
    """Run all tests"""
    print(f"\n{BOLD}{BLUE}Hybrid Mode Test Suite{ENDC}\n")

    try:
        # Test 1: NOTIFY trigger
        notify_ok = await test_notify_trigger()

        # Test 2: Lightweight check performance
        perf_ok = await test_lightweight_check()

        # Summary
        print(f"\n{BLUE}{'='*70}{ENDC}")
        print(f"{BOLD}Test Summary{ENDC}")
        print(f"{BLUE}{'='*70}{ENDC}\n")

        if notify_ok:
            print(f"{GREEN}✓ NOTIFY Mode: WORKING{ENDC}")
            print(f"  Your server will use event-driven mode")
            print(f"  Expected latency: < 10ms")
        else:
            print(f"{YELLOW}⚠ NOTIFY Mode: NOT AVAILABLE{ENDC}")
            print(f"  Your server will use polling mode")
            print(f"  Expected latency: ~1 second")

        if perf_ok:
            print(f"\n{GREEN}✓ Lightweight Check: WORKING{ENDC}")
            print(f"  Polling mode is optimized")

        print(f"\n{BOLD}Next Steps:{ENDC}")
        if notify_ok:
            print(f"  1. {GREEN}NOTIFY is working!{ENDC} Start the server:")
            print(f"     python3 signal_websocket_server.py")
        else:
            print(f"  1. Install NOTIFY trigger:")
            print(f"     {YELLOW}./install_trigger.sh{ENDC}")
            print(f"  2. Start the server:")
            print(f"     python3 signal_websocket_server.py")

        print()

    except Exception as e:
        print(f"\n{RED}Error: {e}{ENDC}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    asyncio.run(main())
