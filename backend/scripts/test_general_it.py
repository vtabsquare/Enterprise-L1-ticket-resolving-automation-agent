"""
test_general_it.py — End-to-end integration test for general_it category.

Steps
-----
A. Verify DB policy row for general_it (send_email, low, allow_auto=True).
B. Create a real Jira ticket worded as a genuine user report.
C. Ingest via IntakeAgent.
D. Run full Orchestrator pipeline.
E. Print DB audit trail.
F. Print relevant raw log lines from logs/app.log.

Usage (from backend/ directory):
    python -m scripts.test_general_it
"""

import sys
import json
import logging
import logging.handlers
import requests
from pathlib import Path
from datetime import datetime, timezone

# ── 1. Load env FIRST ─────────────────────────────────────────────────────────
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ── 2. Configure logging ──────────────────────────────────────────────────────
import structlog

_LOG_FILE = Path(__file__).resolve().parent.parent / "logs" / "app.log"
_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

_shared: list = [
    structlog.contextvars.merge_contextvars,
    structlog.stdlib.add_log_level,
    structlog.stdlib.add_logger_name,
    structlog.processors.TimeStamper(fmt="iso"),
    structlog.processors.StackInfoRenderer(),
    structlog.processors.format_exc_info,
]
_sh = logging.StreamHandler(sys.stdout)
_sh.setFormatter(structlog.stdlib.ProcessorFormatter(
    processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, structlog.dev.ConsoleRenderer()],
    foreign_pre_chain=_shared,
))
_fh = logging.handlers.RotatingFileHandler(str(_LOG_FILE), maxBytes=10*1024*1024, backupCount=5, encoding="utf-8")
_fh.setFormatter(structlog.stdlib.ProcessorFormatter(
    processors=[structlog.stdlib.ProcessorFormatter.remove_processors_meta, structlog.processors.JSONRenderer()],
    foreign_pre_chain=_shared,
))
_root = logging.getLogger()
_root.handlers.clear()
_root.addHandler(_sh)
_root.addHandler(_fh)
_root.setLevel(logging.DEBUG)
structlog.configure(
    processors=_shared + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
    logger_factory=structlog.stdlib.LoggerFactory(),
    wrapper_class=structlog.stdlib.BoundLogger,
    cache_logger_on_first_use=True,
)

# ── 3. App imports ─────────────────────────────────────────────────────────────
from app.config import get_settings
from app.database import get_supabase_client
from app.agents.intake_agent import IntakeAgent
from app.orchestrator import Orchestrator

log = structlog.get_logger(__name__)

REPORTER_EMAIL = "l1bot.test@vtabsquare.com"


def section(title: str) -> None:
    print(f"\n{'='*65}")
    print(f"  {title}")
    print(f"{'='*65}")


# ── A. Verify policy row ───────────────────────────────────────────────────────

def verify_policy() -> None:
    section("A  Verify general_it policy row in DB")
    client = get_supabase_client()
    rows = client.table("policies") \
        .select("policy_name,category,action_type,risk_level,allow_auto,conditions") \
        .eq("category", "general_it") \
        .execute().data
    if not rows:
        print("  ERROR: no general_it policy row found — migration 009 may not have applied")
        sys.exit(1)
    for r in rows:
        print(f"  {json.dumps(r)}")
    send_email_rows = [r for r in rows if r["action_type"] == "send_email"]
    if not send_email_rows:
        print("  ERROR: no send_email row for general_it")
        sys.exit(1)
    r = send_email_rows[0]
    assert r["allow_auto"] is True,   f"allow_auto must be True, got {r['allow_auto']}"
    assert r["risk_level"] == "low",  f"risk_level must be low, got {r['risk_level']}"
    print("  OK — allow_auto=True, risk_level=low")


# ── B. Create Jira ticket ──────────────────────────────────────────────────────

def create_jira_ticket() -> str:
    section("B  Create real Jira ticket (genuine user phrasing)")
    settings = get_settings()
    base_url = settings.jira_base_url.rstrip("/")
    auth = (settings.jira_email, settings.jira_api_token)
    headers = {"Accept": "application/json", "Content-Type": "application/json"}

    summary = "Not sure who to contact — general IT help needed with my workstation setup"
    description = (
        "Hi, I have a few general IT questions about my workstation and I'm not sure "
        "which team to contact or what the right process is. "
        "I'm having some random issues with my computer and honestly not sure if this "
        "falls under IT helpdesk, desktop support, or somewhere else. "
        "Could someone send me some guidance on who handles general IT queries "
        "and what the standard process is for getting help?"
    )

    body = {
        "fields": {
            "project":   {"key": settings.jira_project_key},
            "issuetype": {"name": "Task"},
            "summary":   summary,
            "description": {
                "type": "doc", "version": 1,
                "content": [{"type": "paragraph",
                             "content": [{"type": "text", "text": description}]}],
            },
        }
    }
    resp = requests.post(f"{base_url}/rest/api/3/issue", auth=auth, headers=headers, json=body, timeout=15)
    print(f"  Jira create_issue  HTTP {resp.status_code}")
    if not resp.ok:
        print(f"  ERROR: {resp.text}")
        raise RuntimeError(f"Jira issue creation failed: {resp.status_code}")
    key = resp.json()["key"]
    print(f"  Created: {key}  ({base_url}/browse/{key})")
    log.info("test_general_it: Jira issue created", key=key)
    return key


# ── C. Ingest ─────────────────────────────────────────────────────────────────

def ingest_ticket(issue_key: str) -> str:
    section(f"C  Ingest {issue_key} via IntakeAgent")
    normalized = {
        "source":         "jira",
        "external_id":    issue_key,
        "summary":        "Not sure who to contact — general IT help needed with my workstation setup",
        "description": (
            "Hi, I have a few general IT questions about my workstation and I'm not sure "
            "which team to contact or what the right process is. "
            "I'm having some random issues with my computer and honestly not sure if this "
            "falls under IT helpdesk, desktop support, or somewhere else. "
            "Could someone send me some guidance on who handles general IT queries "
            "and what the standard process is for getting help?"
        ),
        "status":         "open",
        "priority":       "medium",
        "reporter_email": REPORTER_EMAIL,
    }
    ticket = IntakeAgent.process("jira", normalized)
    ticket_id = ticket["id"]
    print(f"  Supabase ticket UUID: {ticket_id}")
    log.info("test_general_it: ticket ingested", ticket_id=ticket_id, jira_key=issue_key)
    return ticket_id


# ── D. Run pipeline ────────────────────────────────────────────────────────────

def run_pipeline(ticket_id: str) -> datetime:
    section(f"D  Orchestrator pipeline — {ticket_id}")
    start = datetime.now(timezone.utc)
    Orchestrator.process_ticket(ticket_id)
    return start


# ── E. DB audit trail ─────────────────────────────────────────────────────────

def print_audit_trail(ticket_id: str, since: datetime) -> None:
    section("E  DB audit trail")
    client = get_supabase_client()
    t = client.table("tickets").select("*").eq("id", ticket_id).execute().data
    if t:
        print(f"  status   : {t[0]['status']}")
        print(f"  category : {t[0]['category']}")
        print(f"  confidence: {t[0].get('confidence')}")
    print()
    rows = client.table("audit_logs") \
        .select("*") \
        .eq("ticket_id", ticket_id) \
        .gte("timestamp", since.isoformat()) \
        .order("timestamp", desc=False) \
        .execute().data
    for row in rows:
        print(f"  [{row['agent_name']:<22}] {row['event_type']:<35} {json.dumps(row['details'])}")


# ── F. Raw log lines ──────────────────────────────────────────────────────────

def show_relevant_logs(ticket_id: str) -> None:
    section(f"F  Relevant raw log lines — {_LOG_FILE}")
    if not _LOG_FILE.exists():
        print("  logs/app.log not found")
        return
    lines = _LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
    for line in lines:
        try:
            obj = json.loads(line)
        except Exception:
            continue
        logger = obj.get("logger", "")
        if "hpack" in logger or "httpcore" in logger:
            continue
        if ticket_id not in line and obj.get("level") not in ("warning", "error"):
            continue
        if ticket_id not in line:
            continue
        ts = obj.get("timestamp", "")[-15:]
        lvl = obj.get("level", "")
        logger_short = logger.split(".")[-1]
        event = obj.get("event", "")
        extra = {k: v for k, v in obj.items() if k not in ("timestamp", "level", "logger", "event")}
        print(f"[{ts}] [{lvl:<7}] [{logger_short:<25}] {event}")
        if extra:
            print(f"  ^ {json.dumps(extra)}")
        print()


# ── Main ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    verify_policy()
    issue_key = create_jira_ticket()
    ticket_id = ingest_ticket(issue_key)
    start_time = run_pipeline(ticket_id)
    print_audit_trail(ticket_id, start_time)
    show_relevant_logs(ticket_id)

    section("DONE")
    print(f"  Jira ticket   : {issue_key}")
    print(f"  Supabase ID   : {ticket_id}")
    print(f"  Reporter email: {REPORTER_EMAIL}")
    print(f"  Log file      : {_LOG_FILE}")
    print()
    print("  Interpret results:")
    print("  - Section E  policy_checked APPROVED   → policy row found, checks passed")
    print("  - Section E  tool_execution_success    → Graph send_email succeeded")
    print("  - Section F  'send_email: sent' + status_code → actual HTTP status")
    print("  - Section E  ticket_resolved           → Jira closed with comment")
    print("  - Section E  ticket_escalated          → see reason in log for failure")
