-- ─────────────────────────────────────────────────────────────────────────────
-- 006_add_reporter_email.sql
-- Add reporter_email column to tickets table so ToolExecutionAgent
-- can use the real reporter's email as the send_email recipient.
-- Run this in: Supabase Dashboard → SQL Editor → New query → Run
-- ─────────────────────────────────────────────────────────────────────────────

ALTER TABLE tickets ADD COLUMN IF NOT EXISTS reporter_email TEXT;

-- ─────────────────────────────────────────────────────────────────────────────
-- End of 006_add_reporter_email.sql
-- ─────────────────────────────────────────────────────────────────────────────
