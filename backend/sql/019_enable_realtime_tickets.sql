-- ─────────────────────────────────────────────────────────────────────────────
-- 019_enable_realtime_tickets.sql
-- Enables Supabase Realtime broadcasting for the `tickets` table so the 
-- dashboard receives instant toast notifications when Jira webhooks fire.
-- ─────────────────────────────────────────────────────────────────────────────

-- Add the 'tickets' table to the built-in supabase_realtime publication
ALTER PUBLICATION supabase_realtime ADD TABLE tickets;
