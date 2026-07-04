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
Full implementation delivered in Phase 6 (Dashboard).
"""

import structlog
from fastapi import APIRouter

log = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/tickets", summary="Dashboard: recent ticket feed")
async def dashboard_tickets():
    return {"items": [], "note": "stub — Phase 6"}


@router.get("/tickets/{ticket_id}", summary="Dashboard: ticket detail")
async def dashboard_ticket_detail(ticket_id: str):
    return {"ticket_id": ticket_id, "note": "stub — Phase 6"}


@router.get("/audit", summary="Dashboard: audit log")
async def dashboard_audit():
    return {"items": [], "note": "stub — Phase 6"}


@router.get("/escalations", summary="Dashboard: open escalations")
async def dashboard_escalations():
    return {"items": [], "note": "stub — Phase 6"}


@router.get("/stats", summary="Dashboard: KPI stats")
async def dashboard_stats():
    return {
        "total_tickets": 0,
        "auto_resolved": 0,
        "escalated": 0,
        "avg_resolution_minutes": 0,
        "note": "stub — Phase 6",
    }


@router.get("/policy-decisions", summary="Dashboard: recent policy decisions")
async def dashboard_policy_decisions():
    return {"items": [], "note": "stub — Phase 6"}
