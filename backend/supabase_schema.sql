-- ─────────────────────────────────────────────────────────────────────────────
-- Supabase Schema — Enterprise Agentic AI L1 Support Automation Platform
--
-- Run this SQL in the Supabase SQL Editor (Dashboard → SQL Editor → New query).
-- Requires the pgvector extension (enabled by default on Supabase).
--
-- Tables:
--   tickets, agent_actions, knowledge_base, policies,
--   resolver_groups, escalations, audit_logs
-- ─────────────────────────────────────────────────────────────────────────────

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- ── Enum types ────────────────────────────────────────────────────────────────

CREATE TYPE ticket_source   AS ENUM ('jira', 'servicenow');
CREATE TYPE ticket_status   AS ENUM ('open', 'in_progress', 'resolved', 'escalated', 'closed');
CREATE TYPE ticket_priority AS ENUM ('low', 'medium', 'high', 'critical');
CREATE TYPE ticket_category AS ENUM (
    'password_reset', 'account_unlock', 'software_access',
    'hardware_issue', 'network_connectivity', 'vpn_access',
    'email_issue', 'onboarding', 'offboarding', 'general_it', 'unknown'
);
CREATE TYPE risk_level      AS ENUM ('low', 'medium', 'high');
CREATE TYPE action_status   AS ENUM (
    'pending', 'approved', 'blocked', 'executing', 'success', 'failed', 'skipped'
);
CREATE TYPE event_type      AS ENUM (
    'ticket_ingested', 'ticket_classified', 'kb_retrieved',
    'plan_generated', 'policy_checked', 'action_executed',
    'ticket_updated', 'ticket_escalated', 'ticket_closed', 'error'
);

-- ── tickets ───────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS tickets (
    id          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    source      ticket_source   NOT NULL,
    external_id TEXT            NOT NULL,
    summary     TEXT            NOT NULL,
    description TEXT,
    category    ticket_category NOT NULL DEFAULT 'unknown',
    priority    ticket_priority NOT NULL DEFAULT 'medium',
    status      ticket_status   NOT NULL DEFAULT 'open',
    confidence  NUMERIC(4,3)    CHECK (confidence >= 0 AND confidence <= 1),
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW(),

    -- Deduplication: one internal record per (source, external_id)
    CONSTRAINT uq_tickets_source_external UNIQUE (source, external_id)
);

CREATE INDEX idx_tickets_status      ON tickets (status);
CREATE INDEX idx_tickets_category    ON tickets (category);
CREATE INDEX idx_tickets_source      ON tickets (source);
CREATE INDEX idx_tickets_created_at  ON tickets (created_at DESC);

-- ── agent_actions ─────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS agent_actions (
    id          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id   UUID            NOT NULL REFERENCES tickets (id) ON DELETE CASCADE,
    agent_name  TEXT            NOT NULL,
    action_type TEXT            NOT NULL,
    payload     JSONB           NOT NULL DEFAULT '{}',
    result      JSONB,
    status      action_status   NOT NULL DEFAULT 'pending',
    created_at  TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_agent_actions_ticket_id  ON agent_actions (ticket_id);
CREATE INDEX idx_agent_actions_status     ON agent_actions (status);
CREATE INDEX idx_agent_actions_created_at ON agent_actions (created_at DESC);

-- ── knowledge_base ────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS knowledge_base (
    id         UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    title      TEXT            NOT NULL,
    content    TEXT            NOT NULL,
    embedding  VECTOR(768),                    -- Gemini text-embedding-004 dimension
    category   ticket_category NOT NULL,
    source     TEXT            NOT NULL DEFAULT 'manual',
    created_at TIMESTAMPTZ     NOT NULL DEFAULT NOW()
);

-- IVFFlat index for approximate nearest-neighbour search (cosine distance)
-- Run AFTER inserting initial data (requires at least ~100 rows for best results)
-- CREATE INDEX idx_kb_embedding ON knowledge_base USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX idx_kb_category   ON knowledge_base (category);
CREATE INDEX idx_kb_created_at ON knowledge_base (created_at DESC);

-- ── policies ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS policies (
    id          UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    policy_name TEXT            NOT NULL UNIQUE,
    category    ticket_category NOT NULL,
    action_type TEXT            NOT NULL,
    risk_level  risk_level      NOT NULL,
    allow_auto  BOOLEAN         NOT NULL DEFAULT FALSE,
    conditions  JSONB           NOT NULL DEFAULT '{}'
    -- conditions example:
    -- { "max_user_count": 1, "require_manager_approval": false, "business_hours_only": true }
);

CREATE INDEX idx_policies_category    ON policies (category);
CREATE INDEX idx_policies_action_type ON policies (action_type);

-- ── resolver_groups ───────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS resolver_groups (
    id                UUID            PRIMARY KEY DEFAULT gen_random_uuid(),
    group_name        TEXT            NOT NULL UNIQUE,
    category          ticket_category NOT NULL,
    jira_queue        TEXT,           -- Jira project/component key
    servicenow_group  TEXT,           -- ServiceNow assignment group name
    escalation_email  TEXT            -- fallback email for notifications

    -- One group per category (can be relaxed later for sub-categories)
);

CREATE UNIQUE INDEX idx_resolver_groups_category ON resolver_groups (category);

-- ── escalations ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS escalations (
    id           UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id    UUID        NOT NULL REFERENCES tickets (id) ON DELETE CASCADE,
    reason       TEXT        NOT NULL,
    escalated_to TEXT        NOT NULL,   -- email or group name
    notified_at  TIMESTAMPTZ,
    resolved_at  TIMESTAMPTZ
);

CREATE INDEX idx_escalations_ticket_id   ON escalations (ticket_id);
CREATE INDEX idx_escalations_resolved_at ON escalations (resolved_at);

-- ── audit_logs ────────────────────────────────────────────────────────────────
-- Append-only. No UPDATE or DELETE allowed (enforced by RLS in Supabase).

CREATE TABLE IF NOT EXISTS audit_logs (
    id         UUID       PRIMARY KEY DEFAULT gen_random_uuid(),
    ticket_id  UUID       REFERENCES tickets (id) ON DELETE SET NULL,
    agent_name TEXT       NOT NULL,
    event_type event_type NOT NULL,
    details    JSONB      NOT NULL DEFAULT '{}',
    timestamp  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    user_id    TEXT        -- populated for manual human actions
);

CREATE INDEX idx_audit_logs_ticket_id  ON audit_logs (ticket_id);
CREATE INDEX idx_audit_logs_event_type ON audit_logs (event_type);
CREATE INDEX idx_audit_logs_timestamp  ON audit_logs (timestamp DESC);

-- ── Row-Level Security — audit_logs is append-only ────────────────────────────
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

-- Service role (backend) can insert
CREATE POLICY audit_insert ON audit_logs
    FOR INSERT
    TO authenticated
    WITH CHECK (TRUE);

-- Service role can select
CREATE POLICY audit_select ON audit_logs
    FOR SELECT
    TO authenticated
    USING (TRUE);

-- No UPDATE or DELETE policies → audit log is immutable

-- ── Seed data: default policies ───────────────────────────────────────────────

INSERT INTO policies (policy_name, category, action_type, risk_level, allow_auto, conditions)
VALUES
    ('Allow auto password reset',  'password_reset',  'password_reset',  'low',    TRUE,  '{"business_hours_only": false}'),
    ('Allow auto account unlock',  'account_unlock',  'ad_unlock',       'low',    TRUE,  '{"max_failed_attempts": 10}'),
    ('Software access — manual',   'software_access', 'group_add',       'medium', FALSE, '{"require_manager_approval": true}'),
    ('VPN access — manual',        'vpn_access',      'group_add',       'medium', FALSE, '{"require_security_approval": true}'),
    ('Hardware — always escalate', 'hardware_issue',  'any',             'high',   FALSE, '{}'),
    ('Onboarding — manual',        'onboarding',      'any',             'medium', FALSE, '{"require_hr_approval": true}')
ON CONFLICT (policy_name) DO NOTHING;

-- ── Seed data: default resolver groups ────────────────────────────────────────

INSERT INTO resolver_groups (group_name, category, jira_queue, servicenow_group, escalation_email)
VALUES
    ('IT Helpdesk L2',    'password_reset',       'SUPPORT',  'IT Helpdesk',        'it-helpdesk@corp.example.com'),
    ('IT Helpdesk L2',    'account_unlock',        'SUPPORT',  'IT Helpdesk',        'it-helpdesk@corp.example.com'),
    ('Software Team',     'software_access',       'SOFTREQ',  'Software Licensing', 'software@corp.example.com'),
    ('Network Team',      'network_connectivity',  'NETOPS',   'Network Operations', 'network@corp.example.com'),
    ('VPN Team',          'vpn_access',            'NETOPS',   'VPN Support',        'vpn@corp.example.com'),
    ('Desktop Support',   'hardware_issue',        'HARDWARE', 'Desktop Support',    'desktop@corp.example.com'),
    ('Email Team',        'email_issue',           'EMAILOPS', 'Email Support',      'email-support@corp.example.com'),
    ('HR-IT Onboarding',  'onboarding',            'HRIT',     'HR-IT',              'hr-it@corp.example.com'),
    ('HR-IT Offboarding', 'offboarding',           'HRIT',     'HR-IT',              'hr-it@corp.example.com'),
    ('IT Helpdesk L2',    'general_it',            'SUPPORT',  'IT Helpdesk',        'it-helpdesk@corp.example.com'),
    ('IT Helpdesk L2',    'unknown',               'SUPPORT',  'IT Helpdesk',        'it-helpdesk@corp.example.com')
ON CONFLICT (group_name) DO NOTHING;

-- ─────────────────────────────────────────────────────────────────────────────
-- End of schema
-- ─────────────────────────────────────────────────────────────────────────────
