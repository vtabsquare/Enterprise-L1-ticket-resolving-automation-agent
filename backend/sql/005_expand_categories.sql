-- ─────────────────────────────────────────────────────────────────────────────
-- 005_expand_categories.sql
-- Expand ticket_category enum with granular VPN, email, and SRS categories.
-- Run this in: Supabase Dashboard → SQL Editor → New query → Run
-- ─────────────────────────────────────────────────────────────────────────────

-- ── 1. Expand the ticket_category ENUM ───────────────────────────────────────

-- VPN subcategories (splitting the old coarse 'vpn_access')
ALTER TYPE ticket_category ADD VALUE IF NOT EXISTS 'vpn_connectivity_issue';
ALTER TYPE ticket_category ADD VALUE IF NOT EXISTS 'vpn_password_reset';
ALTER TYPE ticket_category ADD VALUE IF NOT EXISTS 'vpn_account_unlock';
ALTER TYPE ticket_category ADD VALUE IF NOT EXISTS 'vpn_access_request';
ALTER TYPE ticket_category ADD VALUE IF NOT EXISTS 'vpn_profile_reset';

-- Password / account subcategories
ALTER TYPE ticket_category ADD VALUE IF NOT EXISTS 'password_expiry_assistance';

-- Group / directory
ALTER TYPE ticket_category ADD VALUE IF NOT EXISTS 'group_membership_validation';
ALTER TYPE ticket_category ADD VALUE IF NOT EXISTS 'user_enable_disable';

-- Email / mailbox
ALTER TYPE ticket_category ADD VALUE IF NOT EXISTS 'mailbox_access_issue';
ALTER TYPE ticket_category ADD VALUE IF NOT EXISTS 'outlook_profile_reset';
ALTER TYPE ticket_category ADD VALUE IF NOT EXISTS 'distribution_list_update';
ALTER TYPE ticket_category ADD VALUE IF NOT EXISTS 'mail_forwarding_request';
ALTER TYPE ticket_category ADD VALUE IF NOT EXISTS 'shared_folder_access';

-- Software / endpoint
ALTER TYPE ticket_category ADD VALUE IF NOT EXISTS 'software_install_request';
ALTER TYPE ticket_category ADD VALUE IF NOT EXISTS 'printer_issue';

-- Network
ALTER TYPE ticket_category ADD VALUE IF NOT EXISTS 'network_adapter_issue';
ALTER TYPE ticket_category ADD VALUE IF NOT EXISTS 'dns_flush_guidance';

-- ── 2. Seed policies for each new category ────────────────────────────────────

-- VPN subcategories
INSERT INTO policies (policy_name, category, action_type, risk_level, allow_auto, conditions)
VALUES
    ('VPN connectivity — kb guidance',  'vpn_connectivity_issue',  'send_email', 'low',    TRUE,  '{}'),
    ('VPN password reset — auto',       'vpn_password_reset',      'password_reset', 'low',  TRUE,  '{"business_hours_only": false}'),
    ('VPN account unlock — auto',       'vpn_account_unlock',      'ad_unlock',  'low',    TRUE,  '{}'),
    ('VPN access request — manual',     'vpn_access_request',      'group_add',  'medium', FALSE, '{"require_security_approval": true}'),
    ('VPN profile reset — kb guidance', 'vpn_profile_reset',       'send_email', 'low',    TRUE,  '{}'),

    -- Password / account
    ('Password expiry — kb guidance',   'password_expiry_assistance',  'send_email', 'low',  TRUE,  '{}'),

    -- Group / directory
    ('Group membership — read only',    'group_membership_validation', 'send_email', 'low',  TRUE,  '{}'),
    ('User enable/disable — manual',    'user_enable_disable',         'ad_unlock',  'high', FALSE, '{"require_manager_approval": true}'),

    -- Email / mailbox
    ('Mailbox access — kb guidance',    'mailbox_access_issue',        'send_email', 'low',  TRUE,  '{}'),
    ('Outlook profile — kb guidance',   'outlook_profile_reset',       'send_email', 'low',  TRUE,  '{}'),
    ('Distribution list — escalate',    'distribution_list_update',    'any',        'high', FALSE, '{}'),
    ('Mail forwarding — escalate',      'mail_forwarding_request',     'any',        'high', FALSE, '{}'),
    ('Shared folder — escalate',        'shared_folder_access',        'any',        'medium', FALSE, '{"require_manager_approval": true}'),

    -- Software / endpoint
    ('Software install — escalate',     'software_install_request',    'any',        'high', FALSE, '{}'),
    ('Printer issue — escalate',        'printer_issue',               'any',        'high', FALSE, '{}'),

    -- Network
    ('Network adapter — kb guidance',   'network_adapter_issue',       'send_email', 'low',  TRUE,  '{}'),
    ('DNS flush — kb guidance',         'dns_flush_guidance',          'send_email', 'low',  TRUE,  '{}')

ON CONFLICT (policy_name) DO NOTHING;

-- ── 3. Seed resolver_groups for each new category ─────────────────────────────

INSERT INTO resolver_groups (group_name, category, jira_queue, servicenow_group, escalation_email)
VALUES
    ('VPN Support',         'vpn_connectivity_issue',      'KAN', 'VPN Support',        'vpn@corp.example.com'),
    ('VPN Support',         'vpn_password_reset',          'KAN', 'VPN Support',        'vpn@corp.example.com'),
    ('VPN Support',         'vpn_account_unlock',          'KAN', 'VPN Support',        'vpn@corp.example.com'),
    ('Network Security',    'vpn_access_request',          'KAN', 'Network Security',   'netsec@corp.example.com'),
    ('VPN Support',         'vpn_profile_reset',           'KAN', 'VPN Support',        'vpn@corp.example.com'),
    ('IT Helpdesk L2',      'password_expiry_assistance',  'KAN', 'IT Helpdesk',        'it-helpdesk@corp.example.com'),
    ('IT Helpdesk L2',      'group_membership_validation', 'KAN', 'IT Helpdesk',        'it-helpdesk@corp.example.com'),
    ('IT Helpdesk L2',      'user_enable_disable',         'KAN', 'IT Helpdesk',        'it-helpdesk@corp.example.com'),
    ('Email Team',          'mailbox_access_issue',        'KAN', 'Email Support',      'email-support@corp.example.com'),
    ('Email Team',          'outlook_profile_reset',       'KAN', 'Email Support',      'email-support@corp.example.com'),
    ('Email Team',          'distribution_list_update',    'KAN', 'Email Support',      'email-support@corp.example.com'),
    ('Email Team',          'mail_forwarding_request',     'KAN', 'Email Support',      'email-support@corp.example.com'),
    ('Email Team',          'shared_folder_access',        'KAN', 'Email Support',      'email-support@corp.example.com'),
    ('Desktop Support',     'software_install_request',    'KAN', 'Desktop Support',    'desktop@corp.example.com'),
    ('Desktop Support',     'printer_issue',               'KAN', 'Desktop Support',    'desktop@corp.example.com'),
    ('Network Team',        'network_adapter_issue',       'KAN', 'Network Operations', 'network@corp.example.com'),
    ('Network Team',        'dns_flush_guidance',          'KAN', 'Network Operations', 'network@corp.example.com')
ON CONFLICT (category) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- End of 005_expand_categories.sql
-- ─────────────────────────────────────────────────────────────────────────────
