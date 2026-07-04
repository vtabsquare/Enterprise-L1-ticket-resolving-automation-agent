"""
ticket_router.py — CRUD endpoints for the tickets table.

Endpoints:
  GET    /api/tickets            — list tickets (paginated, filterable)
  GET    /api/tickets/{id}       — get single ticket
  POST   /api/tickets            — manually create ticket (testing / admin)
  PATCH  /api/tickets/{id}       — update ticket fields
  POST   /api/tickets/{id}/reprocess — re-trigger the agent pipeline

Full implementation delivered in Phase 3.
"""

import structlog
from fastapi import APIRouter

log = structlog.get_logger(__name__)
router = APIRouter()


@router.get("/", summary="List all tickets")
async def list_tickets():
    """Returns paginated ticket list. Full implementation in Phase 3."""
    return {"items": [], "total": 0, "note": "stub — Phase 3"}


@router.get("/{ticket_id}", summary="Get single ticket")
async def get_ticket(ticket_id: str):
    """Returns a single ticket by internal UUID. Full implementation in Phase 3."""
    return {"ticket_id": ticket_id, "note": "stub — Phase 3"}


@router.post("/", summary="Manually create ticket")
async def create_ticket():
    """Manually inject a ticket into the pipeline. Full implementation in Phase 3."""
    return {"status": "stub — Phase 3"}


@router.patch("/{ticket_id}", summary="Update ticket")
async def update_ticket(ticket_id: str):
    """Partial update of ticket fields. Full implementation in Phase 3."""
    return {"ticket_id": ticket_id, "note": "stub — Phase 3"}


@router.post("/{ticket_id}/reprocess", summary="Re-trigger agent pipeline")
async def reprocess_ticket(ticket_id: str):
    """Re-runs the agent pipeline for a ticket. Full implementation in Phase 3."""
    return {"ticket_id": ticket_id, "note": "stub — Phase 3"}
