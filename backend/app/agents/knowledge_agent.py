"""
knowledge_agent.py — Retrieves relevant knowledge base articles for a ticket via vector search.
"""

import structlog
from typing import Any

from app.services import supabase_service
from app.services.gemini_service import get_gemini_service
from app.agents.audit_agent import AuditAgent
from app.agents.agent_utils import safe_call

log = structlog.get_logger(__name__)


class KnowledgeAgent:
    @staticmethod
    def retrieve_context(ticket_id: str, match_count: int = 5) -> list[dict[str, Any]]:
        """
        Retrieves top KB matches using vector similarity search.
        
        Args:
            ticket_id: The UUID of the ticket.
            match_count: Maximum number of articles to retrieve.
            
        Returns:
            List of relevant knowledge base articles.
        """
        log.info("KnowledgeAgent starting", ticket_id=ticket_id)
        
        ticket = supabase_service.get_ticket_by_id(ticket_id)
        if not ticket:
            raise ValueError(f"Ticket {ticket_id} not found")

        gemini = get_gemini_service()
        text_to_embed = f"Title: {ticket.get('summary', '')}\n\n{ticket.get('description', '')}"

        try:
            query_embedding = gemini.generate_embedding(text_to_embed)
            matches = supabase_service.similarity_search_kb(query_embedding, match_count=match_count)
        except Exception as e:
            log.error("Knowledge retrieval failed", error=str(e), ticket_id=ticket_id)
            matches = []

        # Log agent action
        safe_call(
            lambda: supabase_service.insert_agent_action({
                "ticket_id": ticket_id,
                "agent_name": "KnowledgeAgent",
                "action_type": "kb_retrieval",
                "result": {"articles_found": len(matches), "top_matches": [m["title"] for m in matches]},
                "status": "success",
            }),
            agent="KnowledgeAgent", ticket_id=ticket_id,
            call="Supabase insert_agent_action",
        )

        # Log audit trail
        AuditAgent.log(
            ticket_id=ticket_id,
            agent_name="KnowledgeAgent",
            event_type="kb_retrieved",
            details={"articles_found": len(matches)}
        )

        log.info("KnowledgeAgent finished", ticket_id=ticket_id, matches_found=len(matches))
        return matches
