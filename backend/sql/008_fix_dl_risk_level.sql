-- ─────────────────────────────────────────────────────────────────────────────
-- 008_fix_dl_risk_level.sql
--
-- Migration 007 set action_type='dl_update' and allow_auto=TRUE on the
-- distribution_list_update policy but left risk_level='high' unchanged.
-- PolicyEngine has a hard floor: any policy with risk_level='high' is
-- unconditionally escalated regardless of allow_auto. This means the
-- dl_update tool handler in ToolExecutionAgent was permanently unreachable.
--
-- Fix: lower risk_level to 'low' so PolicyEngine can reach allow_auto=TRUE
-- and route the plan to ToolExecutionAgent.dl_update().
--
-- Run in: Supabase Dashboard → SQL Editor → New query → Run
-- ─────────────────────────────────────────────────────────────────────────────

UPDATE policies
SET    risk_level = 'low'
WHERE  category   = 'distribution_list_update';
