-- Allow send_email as an alternative resolution path for vpn_password_reset.
-- Gemini may choose this for vaguer wording (e.g. "I can't remember my VPN login password")
-- where sending step-by-step guidance is equally valid.
INSERT INTO public.policies (policy_name, category, action_type, risk_level, allow_auto, conditions)
VALUES (
    'VPN password reset — guidance email',
    'vpn_password_reset',
    'send_email',
    'low',
    TRUE,
    '{}'
);
