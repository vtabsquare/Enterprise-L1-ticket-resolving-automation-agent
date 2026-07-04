-- ─────────────────────────────────────────────────────────────────────────────
-- 009_general_it_policy.sql
--
-- general_it is in the ticket_category enum since migration 001 but never
-- received a policy row in any migration file.  A row was inserted directly
-- into the DB (policy_name='general_it_guidance') without being recorded here,
-- making the schema non-reproducible from source control alone.
--
-- This migration is idempotent:
--   • If the row is absent  → INSERT creates it.
--   • If a row already exists (direct insert) → UPDATE normalises it to the
--     canonical policy_name and values used by all other guidance categories.
--
-- Intended behaviour: for a general_it ticket, Gemini plans send_email,
-- PolicyEngine finds this row (allow_auto=TRUE, risk_level=low), approves it,
-- and ToolExecutionAgent sends a KB guidance email to the reporter.
-- ─────────────────────────────────────────────────────────────────────────────

-- Step 1: Normalise any existing row
UPDATE policies
SET    policy_name = 'General IT — kb guidance',
       action_type = 'send_email',
       risk_level  = 'low',
       allow_auto  = TRUE,
       conditions  = '{}'
WHERE  category    = 'general_it'
AND    action_type = 'send_email';

-- Step 2: Insert only if no send_email row existed (UPDATE would have no-oped)
INSERT INTO policies (policy_name, category, action_type, risk_level, allow_auto, conditions)
SELECT 'General IT — kb guidance', 'general_it', 'send_email', 'low', TRUE, '{}'
WHERE  NOT EXISTS (
    SELECT 1 FROM policies
    WHERE  category    = 'general_it'
    AND    action_type = 'send_email'
);
