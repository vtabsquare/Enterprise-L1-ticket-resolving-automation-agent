"""
dashboard_router.py — Read-only endpoints consumed by the React dashboard.

Endpoints:
  GET /api/dashboard/tickets        — recent tickets with status
  GET /api/dashboard/tickets/{id}   — ticket detail with agent action timeline
  GET /api/dashboard/audit          — paginated audit log
  GET /api/dashboard/escalations    — open escalations
  GET /api/dashboard/stats          — aggregate KPI metrics
  GET /api/dashboard/policy-decisions — recent policy check results

All endpoints are read-only. The dashboard has no write access to the database.

IMPORTANT SECURITY MARKER:
The dashboard is currently unauthenticated for internal development.
Before deploying to production TWO changes are required together — neither alone is sufficient:

1. Auth middleware: inject `Depends(verify_supabase_token)` into every route so only
   authorized administrators can call these endpoints. The React frontend must pass
   the user's Supabase JWT in the Authorization header.

2. Client swap: all six endpoints currently call get_supabase_client(), which uses the
   SERVICE ROLE key and bypasses Supabase RLS entirely. Switching to
   get_supabase_anon_client() (which uses the ANON key) is required so that row-level
   policies are actually enforced. Adding auth middleware without this client swap
   means queries still bypass RLS regardless of whether the user is authenticated.
"""

import structlog
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Query, HTTPException

from app.services.supabase_service import get_supabase_client

log = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/tickets", summary="Dashboard: recent ticket feed")
async def dashboard_tickets(
    status: Optional[str] = None,
    category: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100)
):
    client = get_supabase_client()
    query = client.table("tickets").select("*", count="exact")
    
    if status:
        query = query.eq("status", status)
    if category:
        query = query.eq("category", category)
        
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size - 1
    
    res = query.order("created_at", desc=True).range(start_idx, end_idx).execute()
    
    return {
        "items": res.data,
        "total": res.count,
        "page": page,
        "page_size": page_size
    }


@router.get("/tickets/{ticket_id}", summary="Dashboard: ticket detail")
async def dashboard_ticket_detail(ticket_id: str):
    client = get_supabase_client()
    
    # 1. Fetch ticket
    t_res = client.table("tickets").select("*").eq("id", ticket_id).execute()
    if not t_res.data:
        raise HTTPException(status_code=404, detail="Ticket not found")
    ticket = t_res.data[0]
    
    # 2. Fetch agent_actions
    a_res = client.table("agent_actions").select("*").eq("ticket_id", ticket_id).execute()
    
    # 3. Fetch audit_logs
    al_res = client.table("audit_logs").select("*").eq("ticket_id", ticket_id).execute()
    
    # Combine agent_actions and audit_logs into a single timeline
    timeline = []
    for action in a_res.data:
        timeline.append({
            "type": "agent_action",
            "timestamp": action.get("created_at"),
            "agent_name": action.get("agent_name"),
            "action_type": action.get("action_type"),
            "result": action.get("result"),
            "status": action.get("status")
        })
        
    for audit in al_res.data:
        timeline.append({
            "type": "audit_log",
            "timestamp": audit.get("timestamp"),  # Fix: audit_logs uses timestamp, not created_at
            "agent_name": audit.get("agent_name"),
            "event_type": audit.get("event_type"),
            "details": audit.get("details")
        })
        
    # Sort chronologically, handling potential None timestamps safely
    timeline.sort(key=lambda x: x["timestamp"] or "")
    
    return {
        "ticket": ticket,
        "timeline": timeline
    }


@router.get("/audit", summary="Dashboard: audit log")
async def dashboard_audit(
    ticket_id: Optional[str] = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100)
):
    client = get_supabase_client()
    query = client.table("audit_logs").select("*", count="exact")
    
    if ticket_id:
        query = query.eq("ticket_id", ticket_id)
        
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size - 1
    
    # Fix: audit_logs orders by timestamp, not created_at
    res = query.order("timestamp", desc=True).range(start_idx, end_idx).execute()
    
    return {
        "items": res.data,
        "total": res.count,
        "page": page,
        "page_size": page_size
    }


@router.get("/escalations", summary="Dashboard: open escalations")
async def dashboard_escalations(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100)
):
    client = get_supabase_client()
    # Join with tickets if foreign key exists, otherwise just get escalations
    query = client.table("escalations").select("*, tickets(summary, status)", count="exact")
    
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size - 1
    
    # Fix: escalations orders by notified_at, not created_at
    res = query.order("notified_at", desc=True).range(start_idx, end_idx).execute()
    
    return {
        "items": res.data,
        "total": res.count,
        "page": page,
        "page_size": page_size
    }


@router.get("/stats", summary="Dashboard: KPI stats")
async def dashboard_stats():
    client = get_supabase_client()
    
    # Fix: Fetch all and filter in Python to avoid Cloudflare 500s from unencoded '%' in the URL
    res = client.table("tickets").select("id, status, external_id, created_at").execute()
    
    valid_tickets = [
        t for t in res.data 
        if not (t.get("external_id", "").startswith("TEST-R") or t.get("external_id", "").startswith("KAN-2"))
    ]
    
    total = len(valid_tickets)
    auto_resolved = sum(1 for t in valid_tickets if t.get("status") == "resolved")
    escalated = sum(1 for t in valid_tickets if t.get("status") == "escalated")
    
    # Fix: tickets table does not have updated_at. Fetch resolution timestamps from audit_logs.
    res_audit = client.table("audit_logs").select("ticket_id, timestamp").eq("event_type", "ticket_resolved").execute()
    resolved_times = {row["ticket_id"]: row["timestamp"] for row in res_audit.data}
    
    resolution_times = []
    for t in valid_tickets:
        if t.get("status") == "resolved" and t["id"] in resolved_times:
            created = datetime.fromisoformat(t["created_at"].replace("Z", "+00:00"))
            resolved = datetime.fromisoformat(resolved_times[t["id"]].replace("Z", "+00:00"))
            diff_mins = (resolved - created).total_seconds() / 60.0
            if diff_mins > 0:
                resolution_times.append(diff_mins)
            
    avg_resolution = sum(resolution_times) / len(resolution_times) if resolution_times else 0.0
    
    return {
        "total_tickets": total,
        "auto_resolved": auto_resolved,
        "escalated": escalated,
        "avg_resolution_minutes": round(avg_resolution, 2),
        "test_traffic_excluded": True
    }


@router.get("/policy-decisions", summary="Dashboard: recent policy decisions")
async def dashboard_policy_decisions(
    page: int = Query(1, ge=1),
    page_size: int = Query(25, ge=1, le=100)
):
    client = get_supabase_client()
    query = client.table("audit_logs").select("*", count="exact").eq("event_type", "policy_checked")
    
    start_idx = (page - 1) * page_size
    end_idx = start_idx + page_size - 1
    
    # Fix: audit_logs orders by timestamp, not created_at
    res = query.order("timestamp", desc=True).range(start_idx, end_idx).execute()
    
    return {
        "items": res.data,
        "total": res.count,
        "page": page,
        "page_size": page_size
    }
