"""
classification_agent.py — Uses the LLM to classify an incoming ticket into a standard category.
"""

import structlog
from typing import Any

from app.services import supabase_service
from app.services.gemini_service import get_gemini_service
from app.agents.audit_agent import AuditAgent
from app.agents.agent_utils import safe_call

log = structlog.get_logger(__name__)


class ClassificationAgent:
    @staticmethod
    def process(ticket_id: str) -> dict[str, Any]:
        """
        Retrieves the ticket, classifies it using Gemini, and updates the database.
        
        Args:
            ticket_id: The UUID of the ticket to classify.
            
        Returns:
            The classification result dict: {"category": "...", "confidence": float}
        """
        log.info("ClassificationAgent starting", ticket_id=ticket_id)
        
        ticket = supabase_service.get_ticket_by_id(ticket_id)
        if not ticket:
            raise ValueError(f"Ticket {ticket_id} not found")

        gemini = get_gemini_service()
        
        try:
            result = gemini.classify_ticket(ticket["summary"], ticket.get("description"))
        except Exception as e:
            log.error("Classification failed", error=str(e), ticket_id=ticket_id)
            result = {"category": "unknown", "confidence": 0.0}

        category = result.get("category", "unknown")
        confidence = result.get("confidence", 0.0)

        # Update ticket in DB
        safe_call(
            lambda: supabase_service.update_ticket(
                ticket_id,
                {"category": category, "confidence": confidence}
            ),
            agent="ClassificationAgent", ticket_id=ticket_id,
            call="Supabase update_ticket",
        )

        # Log agent action
        safe_call(
            lambda: supabase_service.insert_agent_action({
                "ticket_id": ticket_id,
                "agent_name": "ClassificationAgent",
                "action_type": "classify",
                "result": result,
                "status": "success",
            }),
            agent="ClassificationAgent", ticket_id=ticket_id,
            call="Supabase insert_agent_action",
        )

        # Log audit trail
        AuditAgent.log(
            ticket_id=ticket_id,
            agent_name="ClassificationAgent",
            event_type="ticket_classified",
            details={"category": category, "confidence": confidence}
        )

        log.info("ClassificationAgent finished", ticket_id=ticket_id, category=category)
        return result
