import pytest
import requests

# MUST RUN SERIALLY - DO NOT USE pytest-xdist or parallel execution (unless using loadgroup mode)
# These tests share and mutate the real state of a single Entra ID test user, 
# so parallel execution will cause false failures via race conditions.
pytestmark = pytest.mark.xdist_group(name="serial")

TEST_USER_EMAIL = "l1bot.test@vtabsquare.com"
HR_GROUP_ID = "c8eee9bb-9482-481b-b3c2-616f99638f68"
HR_GROUP_NAME = "HR Management"
ESCALATE_GROUP_ID = "e26e2ef6-c12e-4100-9e74-997b7bb7aa61"
ESCALATE_GROUP_NAME = "Loan Application"

import time
def get_agent_action(supabase_client, ticket_id, action_type):
    for _ in range(10):
        res = supabase_client.table("agent_actions").select("*").eq("ticket_id", ticket_id).eq("action_type", action_type).execute()
        if res.data:
            return res.data[0]
        time.sleep(0.5)
    return None


# ── Fixtures for Setup/Teardown ───────────────────────────────────────────────

@pytest.fixture
def vpn_account_setup(graph_client):
    """Ensure the account is locked (disabled) before testing unlock."""
    headers = graph_client._get_headers()
    requests.patch(f"https://graph.microsoft.com/v1.0/users/{TEST_USER_EMAIL}", json={"accountEnabled": False}, headers=headers)
    yield
    # NOTE: teardown intentionally does NOT re-disable here — that was a race
    # condition with the test's accountEnabled assertion. The setup phase of
    # the next run re-disables the account before each test.


@pytest.fixture
def password_reset_setup(graph_client):
    """Baseline lastPasswordChangeDateTime by setting to OldPass123!."""
    headers = graph_client._get_headers()
    graph_client.reset_password(TEST_USER_EMAIL, "OldPass123!")
    import time
    time.sleep(2) # Give Graph a moment to persist the new timestamp
    resp = requests.get(f"https://graph.microsoft.com/v1.0/users/{TEST_USER_EMAIL}?$select=lastPasswordChangeDateTime", headers=headers)
    baseline = resp.json().get("lastPasswordChangeDateTime")
    yield baseline
    # No teardown needed; we can't un-reset a password securely without knowing the old one.

@pytest.fixture
def group_validation_escalate_setup(graph_client):
    """Ensure user is NOT in the Escalate test group."""
    headers = graph_client._get_headers()
    members = requests.get(f"https://graph.microsoft.com/v1.0/groups/{ESCALATE_GROUP_ID}/members", headers=headers).json()
    
    # Check if TEST_USER_EMAIL is in the group. Graph API returns user objects.
    user_id = next((m["id"] for m in members.get("value", []) if m.get("userPrincipalName") == TEST_USER_EMAIL or m.get("mail") == TEST_USER_EMAIL), None)
    if not user_id:
        user_resp = requests.get(f"https://graph.microsoft.com/v1.0/users/{TEST_USER_EMAIL}?$select=id", headers=headers).json()
        user_id = user_resp.get("id")

    if any(m["id"] == user_id for m in members.get("value", [])):
        requests.delete(f"https://graph.microsoft.com/v1.0/groups/{ESCALATE_GROUP_ID}/members/{user_id}/$ref", headers=headers)
    yield ESCALATE_GROUP_ID

@pytest.fixture
def group_validation_success_setup(graph_client):
    """Ensure user IS in the HR Management group."""
    headers = graph_client._get_headers()
    members = requests.get(f"https://graph.microsoft.com/v1.0/groups/{HR_GROUP_ID}/members", headers=headers).json()
    
    user_resp = requests.get(f"https://graph.microsoft.com/v1.0/users/{TEST_USER_EMAIL}?$select=id", headers=headers).json()
    user_id = user_resp.get("id")

    if not any(m["id"] == user_id for m in members.get("value", [])):
        requests.post(
            f"https://graph.microsoft.com/v1.0/groups/{HR_GROUP_ID}/members/$ref",
            json={"@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{user_id}"},
            headers=headers
        )
    yield HR_GROUP_ID
    # Teardown: remove them again
    requests.delete(f"https://graph.microsoft.com/v1.0/groups/{HR_GROUP_ID}/members/{user_id}/$ref", headers=headers)


# ── Write Action Tests ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_vpn_account_unlock(jira_client, supabase_client, graph_client, wait_for_ticket_completion, vpn_account_setup):
    issue_key = jira_client.create_test_ticket("VPN locked out", f"My VPN account got locked out. Email: {TEST_USER_EMAIL}")
    test_passed = False
    try:
        ticket = wait_for_ticket_completion(supabase_client, issue_key)
        assert ticket["status"] == "resolved"
        
        # Verify comment
        update_action = get_agent_action(supabase_client, ticket["id"], "update_ticket")
        assert update_action and update_action["payload"].get("comment_posted") is True

        # Verify state change
        headers = graph_client._get_headers()
        account_enabled = None
        for _ in range(5):
            user_data = requests.get(f"https://graph.microsoft.com/v1.0/users/{TEST_USER_EMAIL}?$select=accountEnabled", headers=headers).json()
            account_enabled = user_data.get("accountEnabled")
            if account_enabled is True:
                break
            time.sleep(2)
        assert account_enabled is True

        test_passed = True
    finally:
        if test_passed:
            jira_client.delete_ticket(issue_key)
        else:
            jira_client.update_summary(issue_key, f"[FAILED TEST] {issue_key}")

@pytest.mark.asyncio
async def test_password_reset(jira_client, supabase_client, graph_client, wait_for_ticket_completion, password_reset_setup):
    baseline_time = password_reset_setup
    issue_key = jira_client.create_test_ticket("Password reset", f"I forgot my AD password. Email: {TEST_USER_EMAIL}")
    test_passed = False
    try:
        ticket = wait_for_ticket_completion(supabase_client, issue_key)
        assert ticket["status"] == "resolved"
        
        # Verify state change with eventual consistency polling
        headers = graph_client._get_headers()
        new_time = None
        for _ in range(5):
            user_data = requests.get(f"https://graph.microsoft.com/v1.0/users/{TEST_USER_EMAIL}?$select=lastPasswordChangeDateTime", headers=headers).json()
            new_time = user_data.get("lastPasswordChangeDateTime")
            if new_time != baseline_time:
                break
            time.sleep(2)
        assert new_time != baseline_time

        test_passed = True
    finally:
        if test_passed:
            jira_client.delete_ticket(issue_key)
        else:
            jira_client.update_summary(issue_key, f"[FAILED TEST] {issue_key}")


# ── Group Membership Tests ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_group_validation_nonmember(jira_client, supabase_client, wait_for_ticket_completion, group_validation_escalate_setup):
    issue_key = jira_client.create_test_ticket("Check group access", f"Can you verify I am in {ESCALATE_GROUP_NAME}? Email: {TEST_USER_EMAIL}")
    test_passed = False
    try:
        ticket = wait_for_ticket_completion(supabase_client, issue_key)
        # Non-member: tool sends a "No" answer email and resolves — no longer escalates
        assert ticket["status"] == "resolved"

        plan = get_agent_action(supabase_client, ticket["id"], "generate_plan")
        assert plan["payload"]["action_type"] == "check_group_membership"

        # raw_response must be a real dict with is_member=False — not null, not an error key
        tool_exec = get_agent_action(supabase_client, ticket["id"], "tool_execute")
        assert tool_exec["status"] == "success"
        raw = tool_exec["payload"]["raw_response"]
        assert raw is not None, "raw_response must not be null"
        assert raw.get("is_member") is False
        assert "NOT a member" in raw.get("answer", "")

        test_passed = True
    finally:
        if test_passed:
            jira_client.delete_ticket(issue_key)
        else:
            jira_client.update_summary(issue_key, f"[FAILED TEST] {issue_key}")

@pytest.mark.asyncio
async def test_group_validation_success(jira_client, supabase_client, wait_for_ticket_completion, group_validation_success_setup):
    issue_key = jira_client.create_test_ticket("Check group access", f"Can you verify I am in {HR_GROUP_NAME}? Email: {TEST_USER_EMAIL}")
    test_passed = False
    try:
        ticket = wait_for_ticket_completion(supabase_client, issue_key)
        assert ticket["status"] == "resolved"

        plan = get_agent_action(supabase_client, ticket["id"], "generate_plan")
        assert plan["payload"]["action_type"] == "check_group_membership"

        # raw_response must contain the real membership answer — not null
        tool_exec = get_agent_action(supabase_client, ticket["id"], "tool_execute")
        assert tool_exec["status"] == "success"
        raw = tool_exec["payload"]["raw_response"]
        assert raw is not None, "raw_response must not be null"
        assert raw.get("is_member") is True
        assert "is a member" in raw.get("answer", "")

        test_passed = True
    finally:
        if test_passed:
            jira_client.delete_ticket(issue_key)
        else:
            jira_client.update_summary(issue_key, f"[FAILED TEST] {issue_key}")


# ── Guidance (Email) Tests ────────────────────────────────────────────────────

# A shared helper for pure guidance tests
async def run_guidance_test(jira_client, supabase_client, wait_for_ticket_completion, summary, desc, expected_keyword):
    issue_key = jira_client.create_test_ticket(summary, f"{desc} Email: {TEST_USER_EMAIL}")
    test_passed = False
    try:
        ticket = wait_for_ticket_completion(supabase_client, issue_key)
        assert ticket["status"] == "resolved"
        
        plan = get_agent_action(supabase_client, ticket["id"], "generate_plan")
        assert plan["payload"]["action_type"] == "send_email"
        email_body = plan["payload"]["parameters"].get("body", "").lower()
        
        # Verify the email isn't empty and contains the expected KB term
        assert expected_keyword.lower() in email_body
        
        tool = get_agent_action(supabase_client, ticket["id"], "tool_execute")
        assert tool and tool["status"] == "success"

        test_passed = True
    finally:
        if test_passed:
            jira_client.delete_ticket(issue_key)
        else:
            jira_client.update_summary(issue_key, f"[FAILED TEST] {issue_key}")


@pytest.mark.asyncio
async def test_general_it(jira_client, supabase_client, wait_for_ticket_completion):
    await run_guidance_test(
        jira_client, supabase_client, wait_for_ticket_completion,
        "General IT help question", "I have a general IT question about my benefits portal.",
        expected_keyword="service desk"  # Assuming general_it sends generic acknowledgement
    )

@pytest.mark.asyncio
async def test_password_expiry_assistance(jira_client, supabase_client, wait_for_ticket_completion):
    await run_guidance_test(
        jira_client, supabase_client, wait_for_ticket_completion,
        "Password expiring soon", "I got an email that my password expires in 3 days. What do I do?",
        expected_keyword="ctrl+alt+del"
    )

@pytest.mark.asyncio
async def test_vpn_connectivity_issue(jira_client, supabase_client, wait_for_ticket_completion):
    await run_guidance_test(
        jira_client, supabase_client, wait_for_ticket_completion,
        "VPN won't connect", "I cannot connect to the corporate VPN from home.",
        expected_keyword="globalprotect"
    )

@pytest.mark.asyncio
async def test_vpn_profile_reset(jira_client, supabase_client, wait_for_ticket_completion):
    await run_guidance_test(
        jira_client, supabase_client, wait_for_ticket_completion,
        "VPN profile corrupted", "My VPN profile is broken, need steps to reset it.",
        expected_keyword="uninstall"
    )

@pytest.mark.asyncio
async def test_mailbox_access_issue(jira_client, supabase_client, wait_for_ticket_completion):
    await run_guidance_test(
        jira_client, supabase_client, wait_for_ticket_completion,
        "Can't access shared mailbox", "I need permissions to the HR shared mailbox.",
        expected_keyword="outlook"
    )

@pytest.mark.asyncio
async def test_outlook_profile_reset(jira_client, supabase_client, wait_for_ticket_completion):
    await run_guidance_test(
        jira_client, supabase_client, wait_for_ticket_completion,
        "Outlook crashing", "My Outlook is frozen and crashing on startup. Need profile reset.",
        expected_keyword="control panel"
    )

@pytest.mark.asyncio
async def test_network_adapter_issue(jira_client, supabase_client, wait_for_ticket_completion):
    await run_guidance_test(
        jira_client, supabase_client, wait_for_ticket_completion,
        "Network adapter reset", "My ethernet is not working, can you reset the adapter?",
        expected_keyword="device manager"
    )

@pytest.mark.asyncio
async def test_dns_flush_guidance(jira_client, supabase_client, wait_for_ticket_completion):
    await run_guidance_test(
        jira_client, supabase_client, wait_for_ticket_completion,
        "Flush DNS", "I can't reach the intranet, helpdesk told me to flush DNS.",
        expected_keyword="ipconfig /flushdns"
    )

# ── Phase D: Remaining Categories ─────────────────────────────────────────────

def get_policy_escalation_reason(supabase_client, ticket_id):
    import time
    for _ in range(10):
        res = supabase_client.table("audit_logs").select("*").eq("ticket_id", ticket_id).eq("event_type", "policy_checked").execute()
        if res.data:
            for log_entry in res.data:
                if log_entry["details"].get("outcome") == "escalated":
                    return log_entry["details"].get("reason", "")
        time.sleep(0.5)
    return ""

# (a) Human Judgment
@pytest.mark.asyncio
async def test_software_access(jira_client, supabase_client, wait_for_ticket_completion):
    issue_key = jira_client.create_test_ticket("Need Salesforce", f"Please grant me access to Salesforce. Email: {TEST_USER_EMAIL}")
    test_passed = False
    try:
        ticket = wait_for_ticket_completion(supabase_client, issue_key)
        assert ticket["status"] == "escalated"
        
        plan = get_agent_action(supabase_client, ticket["id"], "generate_plan")
        assert plan["payload"]["action_type"] == "group_add"
        
        reason = get_policy_escalation_reason(supabase_client, ticket["id"])
        assert "requires manual approval" in reason.lower()
        test_passed = True
    finally:
        if test_passed:
            jira_client.delete_ticket(issue_key)
        else:
            jira_client.update_summary(issue_key, f"[FAILED TEST] {issue_key}")

@pytest.mark.asyncio
async def test_network_connectivity_severe(jira_client, supabase_client, wait_for_ticket_completion):
    issue_key = jira_client.create_test_ticket("Network down", f"The internet in Building 3 is completely down. Email: {TEST_USER_EMAIL}")
    test_passed = False
    try:
        ticket = wait_for_ticket_completion(supabase_client, issue_key)
        assert ticket["status"] == "escalated"
        
        plan = get_agent_action(supabase_client, ticket["id"], "generate_plan")
        assert plan["payload"]["action_type"] == "escalate"
        
        reason = get_policy_escalation_reason(supabase_client, ticket["id"])
        assert "explicitly requested escalation" in reason.lower()
        test_passed = True
    finally:
        if test_passed:
            jira_client.delete_ticket(issue_key)
        else:
            jira_client.update_summary(issue_key, f"[FAILED TEST] {issue_key}")

@pytest.mark.asyncio
async def test_network_connectivity_mild(jira_client, supabase_client, wait_for_ticket_completion):
    issue_key = jira_client.create_test_ticket("Network slow", f"My ethernet cable is loose or slow. Email: {TEST_USER_EMAIL}")
    test_passed = False
    try:
        ticket = wait_for_ticket_completion(supabase_client, issue_key)
        assert ticket["status"] == "resolved"
        
        plan = get_agent_action(supabase_client, ticket["id"], "generate_plan")
        assert plan["payload"]["action_type"] == "send_email"
        test_passed = True
    finally:
        if test_passed:
            jira_client.delete_ticket(issue_key)
        else:
            jira_client.update_summary(issue_key, f"[FAILED TEST] {issue_key}")

@pytest.mark.asyncio
async def test_hardware_issue(jira_client, supabase_client, wait_for_ticket_completion):
    issue_key = jira_client.create_test_ticket("Cracked screen", f"My laptop screen is broken. Email: {TEST_USER_EMAIL}")
    test_passed = False
    try:
        ticket = wait_for_ticket_completion(supabase_client, issue_key)
        assert ticket["status"] == "escalated"
        
        plan = get_agent_action(supabase_client, ticket["id"], "generate_plan")
        assert plan["payload"]["action_type"] == "escalate"
        assert any(kw in plan["payload"].get("reasoning", "").lower() for kw in ["physical", "hardware", "human"])
        
        reason = get_policy_escalation_reason(supabase_client, ticket["id"])
        assert "explicitly requested escalation" in reason.lower()
        test_passed = True
    finally:
        if test_passed:
            jira_client.delete_ticket(issue_key)
        else:
            jira_client.update_summary(issue_key, f"[FAILED TEST] {issue_key}")

@pytest.mark.asyncio
async def test_onboarding(jira_client, supabase_client, wait_for_ticket_completion):
    issue_key = jira_client.create_test_ticket("New hire", f"Please provision laptop for new employee John. Email: {TEST_USER_EMAIL}")
    test_passed = False
    try:
        ticket = wait_for_ticket_completion(supabase_client, issue_key)
        assert ticket["status"] == "escalated"
        
        plan = get_agent_action(supabase_client, ticket["id"], "generate_plan")
        assert plan["payload"]["action_type"] == "escalate"
        assert any(kw in plan["payload"].get("reasoning", "").lower() for kw in ["onboarding", "provision", "human"])
        test_passed = True
    finally:
        if test_passed:
            jira_client.delete_ticket(issue_key)
        else:
            jira_client.update_summary(issue_key, f"[FAILED TEST] {issue_key}")

@pytest.mark.asyncio
async def test_user_enable_disable(jira_client, supabase_client, wait_for_ticket_completion):
    issue_key = jira_client.create_test_ticket("Disable account", f"Please disable AD account for terminated employee. Email: {TEST_USER_EMAIL}")
    test_passed = False
    try:
        ticket = wait_for_ticket_completion(supabase_client, issue_key)
        assert ticket["status"] == "escalated"
        
        plan = get_agent_action(supabase_client, ticket["id"], "generate_plan")
        assert plan["payload"]["action_type"] == "escalate"
        assert any(kw in plan["payload"].get("reasoning", "").lower() for kw in ["high-risk", "approval", "human", "manual", "disable", "write"])
        test_passed = True
    finally:
        if test_passed:
            jira_client.delete_ticket(issue_key)
        else:
            jira_client.update_summary(issue_key, f"[FAILED TEST] {issue_key}")

# (b) Missing Automation
@pytest.mark.asyncio
async def test_software_install_request(jira_client, supabase_client, wait_for_ticket_completion):
    issue_key = jira_client.create_test_ticket("Install Visual Studio", f"Can you push VS to my machine? Email: {TEST_USER_EMAIL}")
    test_passed = False
    try:
        ticket = wait_for_ticket_completion(supabase_client, issue_key)
        assert ticket["status"] == "escalated"
        
        plan = get_agent_action(supabase_client, ticket["id"], "generate_plan")
        assert plan["payload"]["action_type"] == "escalate"
        assert any(kw in plan["payload"].get("reasoning", "").lower() for kw in ["endpoint", "route", "desktop support", "human", "manual"])
        test_passed = True
    finally:
        if test_passed:
            jira_client.delete_ticket(issue_key)
        else:
            jira_client.update_summary(issue_key, f"[FAILED TEST] {issue_key}")

@pytest.mark.asyncio
async def test_mail_forwarding_request(jira_client, supabase_client, wait_for_ticket_completion):
    issue_key = jira_client.create_test_ticket("Forward emails", f"Auto-forward my emails while I'm out. Email: {TEST_USER_EMAIL}")
    test_passed = False
    try:
        ticket = wait_for_ticket_completion(supabase_client, issue_key)
        assert ticket["status"] == "escalated"
        
        plan = get_agent_action(supabase_client, ticket["id"], "generate_plan")
        assert plan["payload"]["action_type"] == "escalate"
        assert any(kw in plan["payload"].get("reasoning", "").lower() for kw in ["write", "automated", "email team", "route", "forwarding"])
        test_passed = True
    finally:
        if test_passed:
            jira_client.delete_ticket(issue_key)
        else:
            jira_client.update_summary(issue_key, f"[FAILED TEST] {issue_key}")

@pytest.mark.asyncio
async def test_shared_folder_access(jira_client, supabase_client, wait_for_ticket_completion):
    issue_key = jira_client.create_test_ticket("SharePoint folder", f"Need access to the shared finance drive. Email: {TEST_USER_EMAIL}")
    test_passed = False
    try:
        ticket = wait_for_ticket_completion(supabase_client, issue_key)
        assert ticket["status"] == "escalated"
        
        plan = get_agent_action(supabase_client, ticket["id"], "generate_plan")
        assert plan["payload"]["action_type"] == "escalate"
        assert any(kw in plan["payload"].get("reasoning", "").lower() for kw in ["manager", "workflow", "human", "approval", "not supported"])
        test_passed = True
    finally:
        if test_passed:
            jira_client.delete_ticket(issue_key)
        else:
            jira_client.update_summary(issue_key, f"[FAILED TEST] {issue_key}")

@pytest.mark.asyncio
async def test_printer_issue(jira_client, supabase_client, wait_for_ticket_completion):
    issue_key = jira_client.create_test_ticket("Printer offline", f"Can't print to the office printer. Email: {TEST_USER_EMAIL}")
    test_passed = False
    try:
        ticket = wait_for_ticket_completion(supabase_client, issue_key)
        assert ticket["status"] == "escalated"
        
        plan = get_agent_action(supabase_client, ticket["id"], "generate_plan")
        assert plan["payload"]["action_type"] == "escalate"
        assert any(kw in plan["payload"].get("reasoning", "").lower() for kw in ["endpoint", "desktop", "physical", "human"])
        test_passed = True
    finally:
        if test_passed:
            jira_client.delete_ticket(issue_key)
        else:
            jira_client.update_summary(issue_key, f"[FAILED TEST] {issue_key}")

# (c) VPN Access Request
@pytest.mark.asyncio
async def test_vpn_access_request(jira_client, supabase_client, wait_for_ticket_completion):
    issue_key = jira_client.create_test_ticket("Need VPN", f"Please provision VPN for me. Email: {TEST_USER_EMAIL}")
    test_passed = False
    try:
        ticket = wait_for_ticket_completion(supabase_client, issue_key)
        assert ticket["status"] == "escalated"
        
        plan = get_agent_action(supabase_client, ticket["id"], "generate_plan")
        assert plan["payload"]["action_type"] == "group_add"
        
        reason = get_policy_escalation_reason(supabase_client, ticket["id"])
        # With the fix, it should find the policy (which has allow_auto=FALSE)
        assert "requires manual approval" in reason.lower()
        test_passed = True
    finally:
        if test_passed:
            jira_client.delete_ticket(issue_key)
        else:
            jira_client.update_summary(issue_key, f"[FAILED TEST] {issue_key}")


@pytest.mark.asyncio
async def test_account_unlock(jira_client, supabase_client, graph_client, wait_for_ticket_completion):
    # Part 1: Force disable
    headers = graph_client._get_headers()
    import requests
    user_url = f"https://graph.microsoft.com/v1.0/users/{TEST_USER_EMAIL}"
    requests.patch(user_url, headers=headers, json={"accountEnabled": False}).raise_for_status()
    
    # Wait for graph API to propagate
    import time
    time.sleep(2)

    # Run ticket
    issue_key = jira_client.create_test_ticket("Account locked out", f"I am locked out of my computer, please unlock my account. Email: {TEST_USER_EMAIL}")
    test_passed = False
    try:
        ticket = wait_for_ticket_completion(supabase_client, issue_key, timeout=60)
        assert ticket["status"] == "resolved"
        
        # Verify state change (Graph API can have slight replication delay)
        is_enabled = None
        for _ in range(5):
            user_data = requests.get(f"{user_url}?$select=accountEnabled", headers=headers).json()
            is_enabled = user_data.get("accountEnabled")
            if is_enabled is True:
                break
            time.sleep(2)
        assert is_enabled is True
        
        # Part 2: Run again when already enabled (should resolve but no-op)
        issue_key2 = jira_client.create_test_ticket("Account locked out again", f"I am locked out of my computer, please unlock my account. Email: {TEST_USER_EMAIL}")
        ticket2 = wait_for_ticket_completion(supabase_client, issue_key2)
        assert ticket2["status"] == "resolved"
        
        test_passed = True
    finally:
        if test_passed:
            jira_client.delete_ticket(issue_key)
            jira_client.delete_ticket(issue_key2)
        else:
            jira_client.update_summary(issue_key, f"[FAILED TEST] {issue_key}")
            try:
                jira_client.update_summary(issue_key2, f"[FAILED TEST] {issue_key2}")
            except Exception:
                pass  # issue_key2 may not have been created yet if failure was earlier


@pytest.mark.asyncio
async def test_email_issue(jira_client, supabase_client, wait_for_ticket_completion):
    issue_key = jira_client.create_test_ticket("Email issue", f"I cannot send or receive emails. Outlook shows an error. Email: {TEST_USER_EMAIL}")
    test_passed = False
    try:
        ticket = wait_for_ticket_completion(supabase_client, issue_key)
        assert ticket["status"] == "resolved"
        
        # Verify action
        action = get_agent_action(supabase_client, ticket["id"], "generate_plan")
        assert action["payload"]["action_type"] == "send_email"
        test_passed = True
    finally:
        if test_passed:
            jira_client.delete_ticket(issue_key)
        else:
            jira_client.update_summary(issue_key, f"[FAILED TEST] {issue_key}")


@pytest.mark.asyncio
async def test_vpn_password_reset(jira_client, supabase_client, wait_for_ticket_completion):
    # Test script path
    issue_key1 = jira_client.create_test_ticket("Forgot my VPN password", f"I forgot my VPN password, please reset it. Email: {TEST_USER_EMAIL}")
    
    # Test email path
    issue_key2 = jira_client.create_test_ticket("Can't remember VPN login", f"I can't remember my VPN login password, need it reset please. Email: {TEST_USER_EMAIL}")
    
    test_passed = False
    try:
        ticket1 = wait_for_ticket_completion(supabase_client, issue_key1, timeout=60)
        assert ticket1["status"] == "resolved"
        
        ticket2 = wait_for_ticket_completion(supabase_client, issue_key2)
        assert ticket2["status"] == "resolved"
        
        test_passed = True
    finally:
        if test_passed:
            jira_client.delete_ticket(issue_key1)
            jira_client.delete_ticket(issue_key2)
        else:
            jira_client.update_summary(issue_key1, f"[FAILED TEST] {issue_key1}")


@pytest.mark.asyncio
async def test_dl_update(jira_client, supabase_client, wait_for_ticket_completion):
    issue_key = jira_client.create_test_ticket("Update DL", f"Please add {TEST_USER_EMAIL} to the engineering-team distribution list. Email: {TEST_USER_EMAIL}")
    test_passed = False
    try:
        ticket = wait_for_ticket_completion(supabase_client, issue_key)
        # It escalates because the dummy 'engineering-team' doesn't exist in our test Azure directory
        assert ticket["status"] == "escalated"
        
        # Verify action plan still chose dl_update
        action = get_agent_action(supabase_client, ticket["id"], "generate_plan")
        assert action["payload"]["action_type"] == "dl_update"
        test_passed = True
    finally:
        if test_passed:
            jira_client.delete_ticket(issue_key)
        else:
            jira_client.update_summary(issue_key, f"[FAILED TEST] {issue_key}")
