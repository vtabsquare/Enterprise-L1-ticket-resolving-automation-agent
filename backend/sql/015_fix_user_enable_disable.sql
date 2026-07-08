-- ─────────────────────────────────────────────────────────────────────────────
-- 015_fix_user_enable_disable.sql
-- Fixes the policy mismatch for user_enable_disable.
-- The prompt requires the LLM to propose 'escalate', but the DB row
-- permitted 'ad_unlock'. We update the row to strictly match the prompt.
-- ─────────────────────────────────────────────────────────────────────────────

UPDATE policies
SET action_type = 'escalate',
    allow_auto = FALSE
WHERE category = 'user_enable_disable';
