-- Add 'noop' to action_status enum (for ad_unlock idempotent no-op case)
ALTER TYPE action_status ADD VALUE IF NOT EXISTS 'noop';

-- Add 'tool_execution_noop' to event_type enum (distinct audit trail entry)
ALTER TYPE event_type ADD VALUE IF NOT EXISTS 'tool_execution_noop';
