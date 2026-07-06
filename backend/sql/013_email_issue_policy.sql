-- Add missing send_email policy for email_issue category.
-- Defined in 003_seed_policies.sql comment but never present in the live DB
-- (same source-control gap as general_it, confirmed by direct query 2026-07-06).
INSERT INTO public.policies (policy_name, category, action_type, risk_level, allow_auto, conditions)
VALUES (
    'Allow auto email issue resolution',
    'email_issue',
    'send_email',
    'low',
    TRUE,
    '{"business_hours_only": false}'
);
