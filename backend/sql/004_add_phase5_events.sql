-- ─────────────────────────────────────────────────────────────────────────────
-- 004_add_phase5_events.sql
-- Add new AuditAgent event_types introduced by Phase 5
-- Run this in: Supabase Dashboard → SQL Editor → New query → Run
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TYPE event_type ADD VALUE IF NOT EXISTS 'tool_execution_success';
ALTER TYPE event_type ADD VALUE IF NOT EXISTS 'tool_execution_failed';
ALTER TYPE event_type ADD VALUE IF NOT EXISTS 'ticket_resolved';
ALTER TYPE event_type ADD VALUE IF NOT EXISTS 'ticket_update_failed';
ALTER TYPE event_type ADD VALUE IF NOT EXISTS 'ticket_escalation_failed';
