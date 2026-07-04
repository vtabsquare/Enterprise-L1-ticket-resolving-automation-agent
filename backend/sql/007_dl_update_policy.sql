-- ─────────────────────────────────────────────────────────────────────────────
-- 007_dl_update_policy.sql
-- Change policy for distribution_list_update to allow auto-execution via dl_update
-- Run this in: Supabase Dashboard → SQL Editor → New query → Run
-- ─────────────────────────────────────────────────────────────────────────────

UPDATE policies
SET action_type = 'dl_update',
    allow_auto = TRUE
WHERE category = 'distribution_list_update';

-- ─────────────────────────────────────────────────────────────────────────────
-- End of 007_dl_update_policy.sql
-- ─────────────────────────────────────────────────────────────────────────────
