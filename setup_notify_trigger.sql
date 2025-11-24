-- ============================================================================
-- PostgreSQL NOTIFY Trigger for Signal WebSocket Server
-- ============================================================================
-- This trigger sends instant notifications when new trading signals are added
-- Enables real-time signal broadcasting with < 10ms latency
-- ============================================================================

-- Drop existing objects if they exist (for both old and new schemas)
DROP TRIGGER IF EXISTS trigger_notify_new_signals ON fas.scoring_history;
DROP TRIGGER IF EXISTS trigger_notify_updated_signals ON fas.scoring_history;
DROP TRIGGER IF EXISTS trigger_notify_new_signals ON fas_v2.scoring_history;
DROP TRIGGER IF EXISTS trigger_notify_updated_signals ON fas_v2.scoring_history;
DROP FUNCTION IF EXISTS notify_new_signals();

-- ============================================================================
-- Function: notify_new_signals()
-- ============================================================================
-- Sends PostgreSQL NOTIFY when a qualifying signal is inserted/updated
-- Only notifies for signals that meet the criteria (score_week > 50, etc.)
-- ============================================================================

CREATE OR REPLACE FUNCTION notify_new_signals()
RETURNS TRIGGER AS $$
DECLARE
    payload JSON;
    tp_active BOOLEAN;
BEGIN
    -- Check if trading pair is active
    SELECT is_active INTO tp_active
    FROM public.trading_pairs
    WHERE id = NEW.trading_pair_id;

    -- Only notify if signal meets all criteria
    IF NEW.is_active = true
       AND tp_active = true
       AND NEW.score_week > 50
       AND NEW.score_month > 50
       AND NEW.timestamp >= now() - INTERVAL '32 minutes' THEN

        -- Build compact payload with key information
        payload := json_build_object(
            'event', TG_OP,
            'id', NEW.id,
            'pair_symbol', NEW.pair_symbol,
            'score_week', NEW.score_week,
            'score_month', NEW.score_month,
            'timestamp', NEW.timestamp,
            'action', NEW.recommended_action
        );

        -- Send notification to 'new_signals' channel
        PERFORM pg_notify('new_signals', payload::text);

        -- Log notification (optional, for debugging)
        -- RAISE NOTICE 'NOTIFY sent: %', payload;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- ============================================================================
-- Trigger: ON INSERT
-- ============================================================================
-- Fires when new signals are inserted into scoring_history
-- ============================================================================

CREATE TRIGGER trigger_notify_new_signals
AFTER INSERT ON fas_v2.scoring_history
FOR EACH ROW
EXECUTE FUNCTION notify_new_signals();

-- ============================================================================
-- Trigger: ON UPDATE
-- ============================================================================
-- Fires when signal scores are updated and meet thresholds
-- Only triggers if score_week or score_month changes
-- ============================================================================

CREATE TRIGGER trigger_notify_updated_signals
AFTER UPDATE OF score_week, score_month, is_active ON fas_v2.scoring_history
FOR EACH ROW
WHEN (
    NEW.score_week > 50
    AND NEW.score_month > 50
    AND (
        NEW.score_week IS DISTINCT FROM OLD.score_week
        OR NEW.score_month IS DISTINCT FROM OLD.score_month
        OR NEW.is_active IS DISTINCT FROM OLD.is_active
    )
)
EXECUTE FUNCTION notify_new_signals();

-- ============================================================================
-- Grant permissions (if needed)
-- ============================================================================
-- Allow the WebSocket server user to listen to notifications
-- Replace 'elcrypto' with your actual database user if different
-- ============================================================================

GRANT USAGE ON SCHEMA fas_v2 TO elcrypto;
GRANT SELECT ON fas_v2.scoring_history TO elcrypto;
GRANT SELECT ON public.trading_pairs TO elcrypto;

-- ============================================================================
-- Test the trigger (optional)
-- ============================================================================
-- Uncomment to test trigger functionality

/*
-- Start listening in another session:
-- LISTEN new_signals;

-- Then insert a test signal:
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
    'TESTUSDT',
    NOW(),
    75.5,
    80.2,
    77.0,
    true,
    'BUY'
);

-- You should receive a NOTIFY in the listening session
*/

-- ============================================================================
-- Verification Queries
-- ============================================================================

-- Check if triggers exist
SELECT
    trigger_name,
    event_manipulation,
    event_object_table,
    action_statement
FROM information_schema.triggers
WHERE trigger_name IN ('trigger_notify_new_signals', 'trigger_notify_updated_signals')
ORDER BY trigger_name;

-- Check if function exists
SELECT
    routine_name,
    routine_type,
    data_type
FROM information_schema.routines
WHERE routine_name = 'notify_new_signals';

-- ============================================================================
-- Performance Notes
-- ============================================================================
-- 1. Trigger overhead: ~0.1-0.5ms per INSERT (negligible)
-- 2. NOTIFY is asynchronous and doesn't block transaction commit
-- 3. Payload size: ~200-300 bytes (well under 8KB limit)
-- 4. Multiple listeners: Broadcast to all connected clients automatically
-- ============================================================================

-- ============================================================================
-- Cleanup (if needed)
-- ============================================================================
/*
-- To remove triggers and function:
DROP TRIGGER IF EXISTS trigger_notify_new_signals ON fas_v2.scoring_history;
DROP TRIGGER IF EXISTS trigger_notify_updated_signals ON fas_v2.scoring_history;
DROP FUNCTION IF EXISTS notify_new_signals();
*/
