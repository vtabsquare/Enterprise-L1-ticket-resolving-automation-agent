-- Add DEFAULT now() to escalations.notified_at so it cannot be inserted as NULL silently
ALTER TABLE public.escalations ALTER COLUMN notified_at SET DEFAULT now();

-- Optionally backfill existing nulls
UPDATE public.escalations SET notified_at = now() WHERE notified_at IS NULL;
