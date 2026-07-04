-- ─────────────────────────────────────────────────────────────────────────────
-- 002_seed_knowledge_base.sql
-- Run this in: Supabase Dashboard → SQL Editor → New query → Run
-- ─────────────────────────────────────────────────────────────────────────────

-- 1. Create the pgvector similarity search function
CREATE OR REPLACE FUNCTION match_kb_articles(
    query_embedding vector(768),
    match_count int DEFAULT 5
)
RETURNS TABLE (
    id UUID,
    title TEXT,
    content TEXT,
    category ticket_category,
    similarity FLOAT
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        kb.id,
        kb.title,
        kb.content,
        kb.category,
        -- pgvector's cosine distance operator is `<=>`.
        -- Distance is 0 for identical vectors, so similarity is 1 - distance.
        1 - (kb.embedding <=> query_embedding) AS similarity
    FROM knowledge_base kb
    WHERE kb.embedding IS NOT NULL
    ORDER BY kb.embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- 2. Insert the 6 requested sample articles with NULL embeddings
INSERT INTO knowledge_base (title, content, category, source)
VALUES
(
    'How to Reset Okta Password',
    '1. Go to okta.corp.example.com.\n2. Click "Need help signing in?".\n3. Select "Forgot password".\n4. Enter your corporate email and choose SMS or Okta Verify for MFA verification.\n5. Follow the prompts to create a new password meeting the complexity requirements (14 chars, 1 uppercase, 1 symbol).\nNote: If MFA is also locked, you must contact L2 Support.',
    'password_reset',
    'manual'
),
(
    'Active Directory Account Unlock Procedure',
    'AD accounts lock automatically after 10 failed login attempts.\nTo unlock:\n1. Verify the user identity via Slack manager confirmation or Zoom.\n2. Open ADUC (Active Directory Users and Computers).\n3. Find the user account, right-click -> Properties -> Account tab.\n4. Check "Unlock account" and click Apply.\n5. Remind the user to update any mobile devices with saved old passwords to prevent immediate re-locking.',
    'account_unlock',
    'manual'
),
(
    'Troubleshooting GlobalProtect VPN Connectivity',
    'If a user cannot connect to the GlobalProtect VPN:\n1. Verify their internet connection is stable.\n2. Ensure the GlobalProtect client is updated to at least v6.1.\n3. Check if the user is trying to connect from a geo-blocked country.\n4. Have the user click the hamburger menu -> Settings -> Sign Out, then sign back in to force a token refresh.\n5. If the portal is unreachable, check the status page for known network outages.',
    'vpn_access',
    'manual'
),
(
    'Software Access Request: Jira and Confluence',
    'Access to Jira and Confluence requires manager approval.\n1. Verify that the ticket has an attached approval from the user''s direct manager.\n2. Log into the Atlassian Admin portal.\n3. Search for the user by email.\n4. Add them to the "jira-software-users" and "confluence-users" groups.\n5. If they need a specific project access, assign the project role as requested.\n6. Notify the user and close the ticket.',
    'software_access',
    'manual'
),
(
    'Fixing Common Printer and Hardware Issues',
    'For local printer issues:\n1. Ask the user to restart the printer and their laptop.\n2. Ensure they are on the corp-wifi network, not the guest network.\n3. Reinstall the printer driver via the Self-Service portal.\n\nFor laptop hardware issues (e.g. broken screen, battery swollen):\n1. Do not attempt remote fix.\n2. Immediately escalate to the local Desktop Support team for hardware replacement.\n3. Provide the user''s asset tag in the escalation notes.',
    'hardware_issue',
    'manual'
),
(
    'Outlook Email Sync Issues',
    'If Outlook is not syncing or says "Disconnected":\n1. Check if the user recently changed their password. If so, they need to update it in Outlook.\n2. Open Outlook in Safe Mode (hold Ctrl while opening) to rule out bad add-ins.\n3. If using a Mac, clear the Outlook cache by right-clicking the folder -> Properties -> Empty Cache.\n4. Rebuild the OST file: close Outlook, go to %localappdata%\Microsoft\Outlook, rename the .ost file to .old, and restart Outlook.',
    'email_issue',
    'manual'
);
