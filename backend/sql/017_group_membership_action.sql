-- ─────────────────────────────────────────────────────────────────────────────
-- 017_group_membership_action.sql
-- Updates group_membership_validation policy to use the new action_type
-- 'check_group_membership' instead of hallucinating an email.
-- ─────────────────────────────────────────────────────────────────────────────

UPDATE policies
SET action_type = 'check_group_membership'
WHERE category = 'group_membership_validation';
