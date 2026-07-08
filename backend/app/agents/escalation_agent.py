"""
escalation_agent.py — Handles manual escalations when PolicyEngine blocks/escalates or ToolExecution fails.
"""

import structlog

from app.services import supabase_service
from app.services.servicenow_service import get_servicenow_client
from app.services.jira_service import get_jira_client
from app.agents.audit_agent import AuditAgent
from app.agents.agent_utils import retry_once, safe_call

log = structlog.get_logger(__name__)

class EscalationAgent:
    """
    Routes tickets to human L2 queues by writing an escalation note to the source ITSM
    and recording the escalation in the local database.
    """

    @staticmethod
    def _get_client(source: str):
        if source == "servicenow":
            return get_servicenow_client()
        elif source == "jira":
            return get_jira_client()
        raise ValueError(f"Unknown ITSM source: {source}")

    @staticmethod
    def escalate(ticket_id: str, reason: str) -> None:
        """
        Escalates a ticket by looking up its category resolver group and posting a note.
        """
        log.info("EscalationAgent starting", ticket_id=ticket_id)

        ticket = retry_once(
            lambda: supabase_service.get_ticket_by_id(ticket_id),
            agent="EscalationAgent", ticket_id=ticket_id, call="Supabase get_ticket_by_id",
        )
        if not ticket:
            raise ValueError(f"Ticket {ticket_id} not found")

        source = ticket.get("source", "servicenow")
        external_id = ticket.get("external_id")
        category = ticket.get("category", "unknown")

        # Look up resolver group by category
        try:
            client_db = supabase_service.get_supabase_client()
            resp = client_db.table("resolver_groups").select("*").eq("category", category).execute()
            resolver_group = resp.data[0] if resp.data else {}
        except Exception as e:
            log.warning("Failed to look up resolver group", error=str(e))
            resolver_group = {}

        escalation_target = resolver_group.get("escalation_email", "it-helpdesk@corp.example.com")
        group_name = resolver_group.get("group_name", "L2 Support")

        client = EscalationAgent._get_client(source)

        comment = (
            f"Agentic IT L1 Automation: Routing to {group_name} for manual review.\n"
            f"Reason: {reason}"
        )

        # Best-effort ITSM comment — failure logged but never crashes the pipeline
        comment_posted = safe_call(
            lambda: client.create_comment(external_id, comment),
            agent="EscalationAgent", ticket_id=ticket_id,
            call="Jira/SN create_comment", default=False,
        ) is not False

        try:
            # Record escalation in the escalations table (for Phase 6 dashboard)
            from datetime import datetime, timezone
            retry_once(
                lambda: supabase_service.get_supabase_client().table("escalations").insert({
                    "ticket_id": ticket_id,
                    "reason": reason,
                    "escalated_to": escalation_target,
                    "notified_at": datetime.now(timezone.utc).isoformat()
                }).execute(),
                agent="EscalationAgent", ticket_id=ticket_id, call="Supabase insert escalation",
            )

            # Update ticket status to escalated
            safe_call(
                lambda: supabase_service.get_supabase_client().table("tickets").update({
                    "status": "escalated"
                }).eq("id", ticket_id).execute(),
                agent="EscalationAgent", ticket_id=ticket_id,
                call="Supabase update tickets status"
            )

            # Record action in local DB
            safe_call(
                lambda: supabase_service.insert_agent_action({
                    "ticket_id": ticket_id,
                    "agent_name": "EscalationAgent",
                    "action_type": "escalate",
                    "payload": {
                        "target": escalation_target,
                        "reason": reason,
                        "comment_posted": comment_posted,
                    },
                    "status": "success",
                }),
                agent="EscalationAgent", ticket_id=ticket_id,
                call="Supabase insert_agent_action",
            )

            # Immutable Audit
            AuditAgent.log(
                ticket_id=ticket_id,
                agent_name="EscalationAgent",
                event_type="ticket_escalated",
                details={
                    "reason": reason,
                    "target": escalation_target,
                    "group_name": group_name,
                    "comment_posted": comment_posted,
                }
            )

            log.info(
                "EscalationAgent finished",
                ticket_id=ticket_id,
                target=escalation_target,
                comment_posted=comment_posted,
            )

        except Exception as e:
            log.error("Failed to write escalation data to DB", ticket_id=ticket_id, error=str(e))
            AuditAgent.log(
                ticket_id=ticket_id,
                agent_name="EscalationAgent",
                event_type="ticket_escalation_failed",
                details={"error": str(e)}
            )
            raise

