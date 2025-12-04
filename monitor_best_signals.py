#!/usr/bin/env python3
"""
Real-time Monitor for Best Signals
Polls the database every 10 seconds for signals with Strategy PnL > 180%
Shows last 600 minutes on start.
"""

import asyncio
import os
import logging
import sys
from datetime import datetime
import asyncpg
from dotenv import load_dotenv

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger('SignalMonitor')

# Load env
current_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(os.path.dirname(current_dir), 'win_rate', '.env')
if os.path.exists(env_path):
    load_dotenv(env_path)
else:
    load_dotenv()

# Configuration
DB_CONFIG = {
    'host': os.getenv('DB_HOST', 'localhost'),
    'port': int(os.getenv('DB_PORT', 5432)),
    'database': os.getenv('DB_NAME'),
    'user': os.getenv('DB_USER'),
    'password': os.getenv('DB_PASSWORD')
}

MIN_PNL = 180.0
WINDOW_MINUTES = 600
POLL_INTERVAL = 10

QUERY = f"""
WITH best_strategies AS (
    SELECT DISTINCT ON (strategy_name, signal_type, market_regime)
        strategy_name,
        signal_type,
        market_regime,
        sl_pct,
        ts_activation_pct,
        ts_callback_pct,
        total_pnl_pct,
        string_to_array(
            regexp_replace(
                split_part(strategy_name, '|', 1),
                '[\[\]'']', '', 'g'
            ), ', '
        ) as required_patterns
    FROM optimization.best_parameters
    WHERE total_pnl_pct > {MIN_PNL}
    ORDER BY strategy_name, signal_type, market_regime, total_pnl_pct DESC
),
recent_signals AS (
    SELECT
        sh.id as signal_id,
        sh.pair_symbol,
        sh.timestamp as signal_timestamp,
        sh.total_score,
        tp.exchange_id,
        ARRAY_AGG(DISTINCT sp.pattern_type || '_' || sp.timeframe) as patterns,
        shr.signal_type,
        mr.regime as market_regime
    FROM fas_v2.scoring_history sh
    JOIN fas_v2.sh_patterns shp ON shp.scoring_history_id = sh.id
    JOIN fas_v2.signal_patterns sp ON sp.id = shp.signal_patterns_id
    INNER JOIN public.trading_pairs tp ON tp.pair_symbol = sh.pair_symbol
    LEFT JOIN web.scoring_history_results_v2 shr ON shr.scoring_history_id = sh.id
    LEFT JOIN fas_v2.market_regime mr ON (
        mr.timeframe = '15m'
        AND mr.timestamp <= sh.timestamp
        AND mr.timestamp > sh.timestamp - INTERVAL '1 hour'
    )
    WHERE sh.timestamp >= NOW() - INTERVAL '%s minutes'
        AND tp.exchange_id = 1
        AND tp.contract_type_id = 1
        AND tp.is_active = true
        AND shr.signal_type IS NOT NULL
    GROUP BY sh.id, sh.pair_symbol, sh.timestamp, sh.total_score, tp.exchange_id, shr.signal_type, mr.regime
    HAVING COUNT(DISTINCT sp.id) >= 2
)
SELECT DISTINCT ON (rs.signal_id)
    rs.signal_id,
    rs.pair_symbol,
    rs.signal_timestamp,
    rs.signal_type,
    rs.total_score,
    rs.market_regime,
    bs.strategy_name,
    bs.sl_pct,
    bs.ts_activation_pct,
    bs.ts_callback_pct,
    bs.total_pnl_pct as strategy_pnl
FROM recent_signals rs
JOIN best_strategies bs ON (
    bs.signal_type = rs.signal_type
    AND bs.market_regime = rs.market_regime
    AND rs.patterns @> bs.required_patterns
)
WHERE rs.market_regime IS NOT NULL
ORDER BY rs.signal_id, bs.total_pnl_pct DESC
"""

async def monitor():
    print(f"🚀 Starting Signal Monitor")
    print(f"   Target: Strategy PnL > {MIN_PNL}%")
    print(f"   Window: Last {WINDOW_MINUTES} minutes")
    print(f"   Poll:   Every {POLL_INTERVAL} seconds")
    print("-" * 80)
    print(f"{'TIME':<20} | {'SYMBOL':<10} | {'TYPE':<5} | {'PNL':<8} | {'PARAMS (SL/TS_ACT/TS_CB)'}")
    print("-" * 80)

    seen_ids = set()
    first_run = True

    try:
        conn = await asyncpg.connect(**DB_CONFIG)
        
        while True:
            try:
                rows = await conn.fetch(QUERY % WINDOW_MINUTES)
                
                # Sort by timestamp (oldest first for printing)
                rows.sort(key=lambda x: x['signal_timestamp'])
                
                new_signals = []
                for row in rows:
                    sig_id = row['signal_id']
                    if sig_id not in seen_ids:
                        new_signals.append(row)
                        seen_ids.add(sig_id)
                
                if new_signals:
                    if first_run:
                        print(f"Found {len(new_signals)} existing signals in window:")
                    
                    for s in new_signals:
                        ts_str = s['signal_timestamp'].strftime('%Y-%m-%d %H:%M')
                        params = f"{s['sl_pct']}% / {s['ts_activation_pct']}% / {s['ts_callback_pct']}%"
                        
                        # Color coding
                        pnl_str = f"{s['strategy_pnl']:.1f}%"
                        if s['strategy_pnl'] > 300:
                            pnl_str = f"\033[92m{pnl_str}\033[0m"  # Green
                        
                        print(f"{ts_str:<20} | {s['pair_symbol']:<10} | {s['signal_type']:<5} | {pnl_str:<17} | {params}")
                        
                    if not first_run:
                        # Play sound or visual cue for real-time signals?
                        pass
                
                first_run = False
                await asyncio.sleep(POLL_INTERVAL)
                
            except Exception as e:
                logger.error(f"Error polling DB: {e}")
                await asyncio.sleep(5)
                # Reconnect if needed
                if conn.is_closed():
                    conn = await asyncpg.connect(**DB_CONFIG)

    except KeyboardInterrupt:
        print("\nStopping monitor...")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
    finally:
        if 'conn' in locals() and not conn.is_closed():
            await conn.close()

if __name__ == '__main__':
    try:
        asyncio.run(monitor())
    except KeyboardInterrupt:
        pass
