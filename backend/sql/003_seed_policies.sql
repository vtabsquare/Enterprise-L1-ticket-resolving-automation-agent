-- ─────────────────────────────────────────────────────────────────────────────
-- 003_seed_policies.sql
-- Additional policy rows beyond the defaults seeded in 001_initial_schema.sql.
-- Run in: Supabase Dashboard → SQL Editor
-- ─────────────────────────────────────────────────────────────────────────────

-- These rows demonstrate both approved and escalated policy paths.
-- The schema already seeds: password_reset, account_unlock, software_access,
-- vpn_access, hardware_issue, onboarding.
-- We add: email_issue (auto-allowed, low risk) and network_connectivity (always escalate).

INSERT INTO policies (policy_name, category, action_type, risk_level, allow_auto, conditions)
VALUES

-- ✅ AUTO-APPROVED PATH: password_reset during business hours
-- Demonstrates the approved path. Low risk + low priority = risk_score 1×1 = 1 ≤ threshold.
(
    'Allow auto password reset (business hours)',
    'password_reset',
    'password_reset',
    'low',
    TRUE,
    '{"business_hours_only": true, "max_per_day": 5, "allowed_systems": ["ad", "okta"]}'
),

-- ✅ AUTO-APPROVED PATH: AD account unlock — any time
-- Low risk. Demonstrates approved path even outside business hours.
(
    'Allow auto AD account unlock',
    'account_unlock',
    'ad_unlock',
    'low',
    TRUE,
    '{"max_failed_attempts": 10, "allowed_systems": ["ad"]}'
),

-- ✅ AUTO-APPROVED PATH: Email issue — send instructions
-- Low risk, automated reply with resolution steps.
(
    'Allow auto email issue resolution',
    'email_issue',
    'send_email',
    'low',
    TRUE,
    '{"business_hours_only": false}'
),

-- 🔼 ESCALATE PATH: Software access — requires manager approval
-- allow_auto=false → always escalates regardless of confidence or risk score.
(
    'Software access requires manual approval',
    'software_access',
    'group_add',
    'medium',
    FALSE,
    '{"require_manager_approval": true}'
),

-- 🔼 ESCALATE PATH: Network connectivity — high risk, always escalate
-- risk_score = 3 (high) × 3 (high priority) = 9 > threshold(4) → escalates even if allow_auto=true.
(
    'Network connectivity — high risk escalate',
    'network_connectivity',
    'any',
    'high',
    TRUE,
    '{"require_network_team": true}'
)

ON CONFLICT (policy_name) DO NOTHING;
