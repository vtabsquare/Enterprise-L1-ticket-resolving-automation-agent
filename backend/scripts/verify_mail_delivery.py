"""
verify_mail_delivery.py — Phase A: confirm real delivery of the general_it
guidance email to l1bot.test@vtabsquare.com.

Approach (most authoritative first):
  1. Read the recipient mailbox directly via Graph:
     GET /users/{recipient}/messages  — filter by subject, widen to 7 days.
     If the message is in the inbox, it was DELIVERED (not just accepted).
  2. Report exact receivedDateTime + folder + isRead.
  3. If Mail.Read app permission is missing, report the exact Graph error
     so we know it is a permission gap, not a delivery failure.

Usage (from backend/):
    python -m scripts.verify_mail_delivery
"""

import sys
import json
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from app.services.graph_service import get_graph_service

RECIPIENT = "l1bot.test@vtabsquare.com"
SUBJECT_MATCH = "Guidance on IT Support Services and Processes"


def main() -> None:
    gs = get_graph_service()
    if gs._is_mock:
        print("GraphService is in MOCK mode — cannot verify real delivery.")
        sys.exit(1)

    headers = gs._get_headers()
    since = (datetime.now(timezone.utc) - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")

    print(f"Recipient : {RECIPIENT}")
    print(f"Subject   : {SUBJECT_MATCH}")
    print(f"Window    : last 7 days (since {since})")
    print("=" * 70)

    # Query recipient mailbox messages, newest first, filtered by receivedDateTime
    url = (
        f"https://graph.microsoft.com/v1.0/users/{RECIPIENT}/messages"
        f"?$filter=receivedDateTime ge {since}"
        f"&$select=subject,receivedDateTime,isRead,from,parentFolderId,sender"
        f"&$orderby=receivedDateTime desc&$top=50"
    )
    resp = requests.get(url, headers=headers)
    print(f"GET /users/{RECIPIENT}/messages  → HTTP {resp.status_code}")

    if not resp.ok:
        print("\nGraph error body (verbatim):")
        print(json.dumps(resp.json(), indent=2) if resp.text else "(empty)")
        print("\nRESULT: could NOT read mailbox — this is a permission/access issue,")
        print("        NOT proof of delivery failure. See error code above.")
        sys.exit(2)

    messages = resp.json().get("value", [])
    print(f"Messages in last 7 days: {len(messages)}")
    print()

    matches = [m for m in messages if SUBJECT_MATCH.lower() in (m.get("subject") or "").lower()]

    if matches:
        print(f"MATCH FOUND — {len(matches)} message(s) with the target subject:")
        for m in matches:
            frm = (m.get("from") or {}).get("emailAddress", {}).get("address", "?")
            print(f"  subject         : {m.get('subject')}")
            print(f"  receivedDateTime: {m.get('receivedDateTime')}")
            print(f"  from            : {frm}")
            print(f"  isRead          : {m.get('isRead')}")
            print()
        print("RESULT: DELIVERED — message is present in the recipient inbox (observed).")
    else:
        print("NO MATCH for the target subject in the last 7 days.")
        print("Most recent 10 subjects actually in the mailbox (for context):")
        for m in messages[:10]:
            print(f"  [{m.get('receivedDateTime')}] {m.get('subject')}")
        print()
        print("RESULT: NOT found in inbox. Next: check junk/other folders, transport rules.")


if __name__ == "__main__":
    main()
