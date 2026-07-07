"""
ticket_update_agent.py — Updates the source ITSM ticket after successful tool execution.
"""

import time
import structlog

from app.schemas.execution import ExecutionResult
from app.services import supabase_service
from app.services.servicenow_service import get_servicenow_client
from app.services.jira_service import get_jira_client
from app.agents.audit_agent import AuditAgent
from app.agents.agent_utils import safe_call

log = structlog.get_logger(__name__)


def _retry_once(fn, *, ticket_id: str, call: str):
    """Run fn(); on any exception wait 2 s and retry once, then re-raise."""
    try:
        return fn()
    except Exception as e:
        log.warning(
            "Supabase call failed — retrying once",
            ticket_id=ticket_id,
            call=call,
            error=str(e),
        )
        time.sleep(2)
        return fn()


class TicketUpdateAgent:
    """
    Updates the source ticket (Jira/ServiceNow) with resolution notes
    and closes the ticket after a successful auto-resolution.
    """

    @staticmethod
    def _get_client(source: str):
        if source == "servicenow":
            return get_servicenow_client()
        elif source == "jira":
            return get_jira_client()
        raise ValueError(f"Unknown ITSM source: {source}")

    @staticmethod
    def resolve_ticket(ticket_id: str, execution_result: ExecutionResult) -> None:
        """
        Writes a resolution note and closes the ticket in the ITSM system.
        """
        log.info("TicketUpdateAgent starting", ticket_id=ticket_id)

        ticket = _retry_once(
            lambda: supabase_service.get_ticket_by_id(ticket_id),
            ticket_id=ticket_id, call="get_ticket_by_id",
        )
        if not ticket:
            raise ValueError(f"Ticket {ticket_id} not found")

        source = ticket.get("source", "servicenow")
        external_id = ticket.get("external_id")
        
        client = TicketUpdateAgent._get_client(source)

        # Format the resolution comment
        comment = (
            "Agentic IT L1 Automation: Successfully resolved this ticket.\n"
            f"Action performed: {execution_result.message}\n"
            f"Status: Auto-resolved."
        )

        # Best-effort ITSM writes — failures logged but never crash the pipeline
        comment_posted = safe_call(
            lambda: client.create_comment(external_id, comment),
            agent="TicketUpdateAgent", ticket_id=ticket_id,
            call="Jira/SN create_comment", default=False,
        ) is not False

        ticket_closed = safe_call(
            lambda: client.close_ticket(external_id),
            agent="TicketUpdateAgent", ticket_id=ticket_id,
            call="Jira/SN close_ticket", default=False,
        ) is not False

        # DB writes are more critical — still wrapped, but re-raise on failure
        try:
            # Update local Supabase DB to mark the ticket as resolved
            _retry_once(
                lambda: supabase_service.update_ticket(ticket_id, {"status": "resolved"}),
                ticket_id=ticket_id, call="update_ticket",
            )

            # Log Agent Action
            safe_call(
                lambda: supabase_service.insert_agent_action({
                    "ticket_id": ticket_id,
                    "agent_name": "TicketUpdateAgent",
                    "action_type": "update_ticket",
                    "payload": {
                        "status": "resolved",
                        "comment": comment,
                        "comment_posted": comment_posted,
                        "ticket_closed": ticket_closed,
                    },
                    "status": "success",
                }),
                agent="TicketUpdateAgent", ticket_id=ticket_id,
                call="Supabase insert_agent_action",
            )

            # Immutable Audit
            AuditAgent.log(
                ticket_id=ticket_id,
                agent_name="TicketUpdateAgent",
                event_type="ticket_resolved",
                details={
                    "external_id": external_id,
                    "source": source,
                    "comment_posted": comment_posted,
                    "ticket_closed": ticket_closed,
                }
            )

            log.info(
                "TicketUpdateAgent finished",
                ticket_id=ticket_id,
                comment_posted=comment_posted,
                ticket_closed=ticket_closed,
            )

        except Exception as e:
            log.error("Failed to write resolution data to DB", ticket_id=ticket_id, error=str(e))
            AuditAgent.log(
                ticket_id=ticket_id,
                agent_name="TicketUpdateAgent",
                event_type="ticket_update_failed",
                details={"error": str(e)}
            )
            raise
