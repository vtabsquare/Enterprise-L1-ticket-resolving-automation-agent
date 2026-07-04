"""
test_dl_update.py — End-to-end integration test for distribution_list_update.

Steps
-----
1. Apply risk_level='low' fix to the policies table via Supabase.
2. Create a real Jira issue with a clear DL-add request.
3. Ingest it into Supabase via IntakeAgent.
4. Run the full Orchestrator pipeline.
5. Print the DB audit trail.
6. Print the last N lines from logs/app.log (raw JSON — no paraphrasing).

Usage (from backend/ directory):
    python -m scripts.test_dl_update
"""

import sys
import os
import json
import logging
import logging.handlers
import requests
from pathlib import Path
from datetime import datetime, timezone

# ── 1. Load env FIRST, before any app import ──────────────────────────────────
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ── 2. Configure logging (mirrors main.py) before any structlog call ──────────
import structlog

_LOG_FILE = Path(__file__).resolve().parent.parent / "logs" / "app.log"
_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

_shared_pre_chain: list = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
]

_stream_handler = logging.StreamHandler(sys.stdout)
_stream_handler.setFormatter(structlog.stdlib.ProcessorFormatter(
    processors=[
        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
        structlog.dev.ConsoleRenderer(),
    ],
    foreign_pre_chain=_shared_pre_chain,
))

_file_handler = logging.handlers.RotatingFileHandler(
    str(_LOG_FILE), maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
)
_file_handler.setFormatter(structlog.stdlib.ProcessorFormatter(
    processors=[
        structlog.stdlib.ProcessorFormatter.remove_processors_meta,
        structlog.processors.JSONRenderer(),
    ],
    foreign_pre_chain=_shared_pre_chain,
))

_root = logging.getLogger()
_root.handlers.clear()
_root.addHandler(_stream_handler)
_root.addHandler(_file_handler)
_root.setLevel(logging.DEBUG)

structlog.configure(
    processors=_shared_pre_chain + [
        structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
    ],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

# ── 3. Now safe to import app modules ─────────────────────────────────────────
from app.config import get_settings
from app.database import get_supabase_client
from app.agents.intake_agent import IntakeAgent
from app.orchestrator import Orchestrator

log = structlog.get_logger(__name__)

# ── Target addresses ───────────────────────────────────────────────────────────
TARGET_USER_EMAIL = "l1bot.test@vtabsquare.com"
TARGET_LIST_EMAIL = "l1testdl@vtabsquare.com"


def section(title: str) -> None:
    print(f"\n{'='*65}")
    print(f"  {title}")
    print(f"{'='*65}")


# ── Step A: Apply the policy fix ───────────────────────────────────────────────

def apply_policy_fix() -> None:
    section("A  Apply policies fix: distribution_list_update risk_level → low")

    client = get_supabase_client()
    result = client.table("policies") \
        .update({"risk_level": "low"}) \
        .eq("category", "distribution_list_update") \
        .execute()

    rows = result.data or []
    if rows:
        r = rows[0]
        print(f"  Updated row  → category={r['category']}  "
              f"action_type={r['action_type']}  "
              f"allow_auto={r['allow_auto']}  "
              f"risk_level={r['risk_level']}")
    else:
        print("  WARNING: update returned no rows — policy may already be 'low' "
              "or Supabase PostgREST is not returning updated rows.")

    # Verify: re-read the row
    verify = client.table("policies") \
        .select("policy_name,category,action_type,allow_auto,risk_level") \
        .eq("category", "distribution_list_update") \
        .execute()
    print(f"\n  DB state after fix:")
    for row in verify.data:
        print(f"    {json.dumps(row)}")


# ── Step B: Create real Jira issue ─────────────────────────────────────────────

def create_jira_ticket() -> str:
    section("B  Create real Jira ticket")

    settings = get_settings()
    base_url = settings.jira_base_url.rstrip("/")
    auth = (settings.jira_email, settings.jira_api_token)
    headers = {"Accept": "application/json", "Content-Type": "application/json"}

    summary = (
        f"Please add {TARGET_USER_EMAIL} to "
        f"distribution list {TARGET_LIST_EMAIL}"
    )
    description_text = (
        f"Hi IT team, please add {TARGET_USER_EMAIL} to the "
        f"distribution list {TARGET_LIST_EMAIL}. "
        f"This is required for Q3 project communications."
    )

    body = {
        "fields": {
            "project":   {"key": settings.jira_project_key},
            "issuetype": {"name": "Task"},
            "summary":   summary,
            "description": {
                "type": "doc", "version": 1,
                "content": [{
                    "type": "paragraph",
                    "content": [{"type": "text", "text": description_text}],
                }],
            },
        }
    }

    resp = requests.post(
        f"{base_url}/rest/api/3/issue",
        auth=auth,
        headers=headers,
        json=body,
        timeout=15,
    )

    print(f"  Jira create_issue  HTTP {resp.status_code}")
    if not resp.ok:
        print(f"  ERROR: {resp.text}")
        raise RuntimeError(f"Jira issue creation failed: {resp.status_code}")

    issue_key = resp.json()["key"]
    print(f"  Created: {issue_key}  ({base_url}/browse/{issue_key})")
    log.info("test_dl_update: Jira issue created", key=issue_key)
    return issue_key


# ── Step C: Ingest into Supabase ───────────────────────────────────────────────

def ingest_ticket(issue_key: str) -> str:
    section(f"C  Ingest {issue_key} via IntakeAgent")

    normalized = {
        "source":         "jira",
        "external_id":    issue_key,
        "summary": (
            f"Please add {TARGET_USER_EMAIL} to "
            f"distribution list {TARGET_LIST_EMAIL}"
        ),
        "description": (
            f"Hi IT team, please add {TARGET_USER_EMAIL} to the "
            f"distribution list {TARGET_LIST_EMAIL}. "
            f"This is required for Q3 project communications."
        ),
        "status":         "open",
        "priority":       "medium",
        "reporter_email": TARGET_USER_EMAIL,
    }

    ticket = IntakeAgent.process("jira", normalized)
    ticket_id = ticket["id"]
    print(f"  Supabase ticket UUID: {ticket_id}")
    log.info("test_dl_update: ticket ingested", ticket_id=ticket_id, jira_key=issue_key)
    return ticket_id


# ── Step D: Run the full pipeline ──────────────────────────────────────────────

def run_pipeline(ticket_id: str) -> datetime:
    section(f"D  Orchestrator pipeline — ticket {ticket_id}")
    start = datetime.now(timezone.utc)
    Orchestrator.process_ticket(ticket_id)
    return start


# ── Step E: DB audit trail ─────────────────────────────────────────────────────

def print_audit_trail(ticket_id: str, since: datetime) -> None:
    section("E  DB audit trail")

    client = get_supabase_client()

    ticket_resp = client.table("tickets").select("*").eq("id", ticket_id).execute()
    if ticket_resp.data:
        t = ticket_resp.data[0]
        print(f"  Final ticket status : {t['status']}")
        print(f"  category            : {t['category']}")
        print(f"  confidence          : {t.get('confidence')}")

    print()
    logs = client.table("audit_logs") \
        .select("*") \
        .eq("ticket_id", ticket_id) \
        .gte("timestamp", since.isoformat()) \
        .order("timestamp", desc=False) \
        .execute()

    for row in logs.data:
        agent  = row.get("agent_name", "?")
        event  = row.get("event_type", "?")
        details = row.get("details", {})
        print(f"  [{agent:<22}] {event:<35} {json.dumps(details)}")


# ── Step F: Raw log tail ───────────────────────────────────────────────────────

def show_log_tail(n: int = 80) -> None:
    section(f"F  Raw log lines (last {n}) — {_LOG_FILE}")

    if not _LOG_FILE.exists():
        print("  logs/app.log does not exist — no lines written yet.")
        return

    lines = _LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    tail = lines[-n:] if len(lines) >= n else lines
    for line in tail:
        print(line)


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    apply_policy_fix()
    issue_key = create_jira_ticket()
    ticket_id = ingest_ticket(issue_key)
    start_time = run_pipeline(ticket_id)
    print_audit_trail(ticket_id, start_time)
    show_log_tail(n=80)

    section("DONE")
    print(f"  Jira ticket : {issue_key}")
    print(f"  Supabase ID : {ticket_id}")
    print(f"  Log file    : {_LOG_FILE}")
    print()
    print("  Interpret results:")
    print("  - Section E  policy_checked outcome=APPROVED   → policy fix worked")
    print("  - Section E  tool_execution_success            → Graph call succeeded")
    print("  - Section F  look for 'dl_update' + Graph HTTP → actual API evidence")
    print("  - Section E  ticket_escalated                  → see reason for failure")
