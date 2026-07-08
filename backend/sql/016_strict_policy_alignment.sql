-- ─────────────────────────────────────────────────────────────────────────────
-- 016_strict_policy_alignment.sql
-- Updates escalation policies to use strict 'escalate' action_type instead of
-- wildcard 'any'. Also inserts missing policy rows for offboarding and unknown.
-- ─────────────────────────────────────────────────────────────────────────────

-- 1. Update existing 'any' policies to strict 'escalate'
UPDATE policies
SET action_type = 'escalate'
WHERE category IN (
    'software_install_request',
    'mail_forwarding_request',
    'shared_folder_access',
    'hardware_issue',
    'printer_issue',
    'onboarding'
) AND action_type = 'any';

-- 2. Insert missing categories to prevent PolicyEngine crashes
INSERT INTO policies (policy_name, category, action_type, risk_level, allow_auto, conditions)
VALUES
    ('Offboarding — escalate', 'offboarding', 'escalate', 'high', FALSE, '{}'),
    ('Unknown category — escalate', 'unknown', 'escalate', 'high', FALSE, '{}')
ON CONFLICT (policy_name) DO NOTHING;
