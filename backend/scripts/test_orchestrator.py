import sys
import json
import structlog
from dotenv import load_dotenv

# Load env before importing app modules
load_dotenv()

from app.orchestrator import Orchestrator
from app.services import supabase_service

log = structlog.get_logger(__name__)

def print_trace(ticket_id: str, start_time):
    print(f"\n{'='*60}")
    print(f"PIPELINE TRACE FOR TICKET: {ticket_id}")
    print(f"{'='*60}\n")
    
    db = supabase_service.get_supabase_client()
    
    # 1. Ticket state
    resp = db.table("tickets").select("*").eq("id", ticket_id).execute()
    if not resp.data:
        print("Ticket not found in DB.")
        return
    ticket = resp.data[0]
    print(f"[{'TICKET'.ljust(15)}] Category: {ticket.get('category')} | Priority: {ticket.get('priority')} | Status: {ticket.get('status')}")
    print(f"                  Summary: {ticket.get('summary')}")
    print("-" * 60)
    
    # 2. Audit logs (chronological, strictly since this script run started)
    resp = db.table("audit_logs").select("*").eq("ticket_id", ticket_id).gte("timestamp", start_time.isoformat()).order("timestamp", desc=False).execute()
    if not resp.data:
        print("No audit logs found.")
        return
        
    for idx, row in enumerate(resp.data):
        agent = row.get("agent_name", "Unknown")
        event = row.get("event_type", "unknown")
        details = row.get("details", {})
        
        print(f"[{agent.ljust(15)}] Event: {event}")
        
        # Format details clearly based on event type
        if event == "ticket_classified":
            print(f"                  Category: {details.get('category')} (Confidence: {details.get('confidence')})")
        elif event == "kb_retrieved":
            print(f"                  Articles Found: {details.get('articles_found')}")
        elif event == "plan_generated":
            print(f"                  Action: {details.get('action_type')} | Target: {details.get('target_system')}")
        elif event == "policy_checked":
            print(f"                  Outcome: {details.get('outcome')} | Reason: {details.get('reason')}")
        elif event == "tool_execution_success":
            print(f"                  Result: {details.get('message')}")
        elif event == "tool_execution_failed":
            print(f"                  Result: {details.get('message')} | Retries: {details.get('retries')}")
        elif event == "ticket_escalated":
            print(f"                  Target: {details.get('target')} | Reason: {details.get('reason')}")
        elif event == "ticket_resolved":
            print(f"                  Action: Ticket closed in {details.get('source')} (External ID: {details.get('external_id')})")
        else:
            print(f"                  Details: {json.dumps(details)}")
        
        print("-" * 60)
        
    print("\nOrchestrator pipeline complete.")

def main():
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.test_orchestrator <ticket_id>")
        sys.exit(1)

    from datetime import datetime, timezone
    start_time = datetime.now(timezone.utc)
    
    print(f"Starting Orchestrator for ticket {ticket_id}...")
    
    try:
        Orchestrator.process_ticket(ticket_id)
        print_trace(ticket_id, start_time)
    except Exception as e:
        log.exception("Orchestrator test failed", error=str(e))
        print(f"\nError running pipeline: {str(e)}")

if __name__ == "__main__":
    main()
