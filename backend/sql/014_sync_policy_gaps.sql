-- 014_sync_policy_gaps.sql
-- Resolves gaps discovered between migration files and the live database.

INSERT INTO policies (policy_name, category, action_type, risk_level, allow_auto, conditions)
VALUES 
-- 1. Defined in 003_seed_policies.sql but missing from live DB
(
    'Network connectivity — high risk escalate',
    'network_connectivity',
    'any',
    'high',
    TRUE,
    '{"require_network_team": true}'
),

-- 2. Present in live DB but never committed to source control
(
    'network_connectivity_guidance',
    'network_connectivity',
    'send_email',
    'low',
    TRUE,
    '{}'
),
(
    'Password expiry — reset',
    'password_expiry_assistance',
    'password_reset',
    'low',
    TRUE,
    '{}'
),
(
    'password_reset_guidance',
    'password_reset',
    'send_email',
    'low',
    TRUE,
    '{}'
)
ON CONFLICT (policy_name) DO NOTHING;
