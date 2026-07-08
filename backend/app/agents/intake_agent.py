"""
intake_agent.py — Handles ingestion, deduplication, and initial persistence of tickets.
"""

import structlog
from typing import Any

from app.services import supabase_service
from app.agents.audit_agent import AuditAgent
from app.agents.agent_utils import retry_once, safe_call

log = structlog.get_logger(__name__)


def _get_ticket_by_external_id(source: str, external_id: str) -> dict[str, Any] | None:
    return supabase_service.get_ticket_by_external_id(source, external_id)


def _insert_ticket_with_commit_check(
    source: str,
    external_id: str,
    normalized_ticket: dict[str, Any],
) -> dict[str, Any]:
    for attempt in range(2):
        try:
            return supabase_service.insert_ticket(normalized_ticket)
        except Exception as e:
            log.warning(
                "Ticket insert failed - checking for committed row before retry",
                source=source,
                external_id=external_id,
                attempt=attempt + 1,
                error=str(e),
            )
            existing_ticket = retry_once(
                lambda: _get_ticket_by_external_id(source, external_id),
                agent="IntakeAgent", ticket_id=None, call="Supabase get_ticket_by_external_id",
            )
            if existing_ticket:
                return existing_ticket
            if attempt == 1:
                raise

    raise RuntimeError(f"Failed to insert ticket for {source}:{external_id}")


class IntakeAgent:
    @staticmethod
    def process(source: str, normalized_ticket: dict[str, Any]) -> dict[str, Any]:
        """
        Receives a normalized ticket from a webhook, deduplicates it,
        persists it to the database, and logs the intake audit event.

        Args:
            source: The source system (e.g., "jira" or "servicenow").
            normalized_ticket: The parsed ticket fields.

        Returns:
            The inserted or updated ticket row from the DB.
        """
        external_id = normalized_ticket.get("external_id")
        if not external_id:
            raise ValueError("Missing external_id in normalized ticket")

        log.info("IntakeAgent processing ticket", source=source, external_id=external_id)

        # 1. Deduplication check
        existing_ticket = retry_once(
            lambda: _get_ticket_by_external_id(source, external_id),
            agent="IntakeAgent", ticket_id=None, call="Supabase get_ticket_by_external_id",
        )

        if existing_ticket:
            log.info("Ticket already exists, updating", ticket_id=existing_ticket["id"])
            update_data = {
                "summary": normalized_ticket.get("summary"),
                "description": normalized_ticket.get("description"),
                "status": normalized_ticket.get("status"),
                "priority": normalized_ticket.get("priority"),
            }
            ticket = retry_once(
                lambda: supabase_service.update_ticket(existing_ticket["id"], update_data),
                agent="IntakeAgent", ticket_id=existing_ticket["id"], call="Supabase update_ticket",
            )
            action = "updated"
        else:
            log.info("New ticket, inserting into DB")
            ticket = _insert_ticket_with_commit_check(source, external_id, normalized_ticket)
            action = "inserted"

        ticket_id = ticket["id"]

        # 2. Write agent_action log
        safe_call(
            lambda: retry_once(
                lambda: supabase_service.insert_agent_action({
                    "ticket_id": ticket_id,
                    "agent_name": "IntakeAgent",
                    "action_type": f"ticket_{action}",
                    "payload": {"source": source, "external_id": external_id},
                    "status": "success",
                }),
                agent="IntakeAgent", ticket_id=ticket_id, call="Supabase insert_agent_action",
            ),
            agent="IntakeAgent", ticket_id=ticket_id,
            call="Supabase insert_agent_action",
        )

        # 3. Write immutable audit log
        AuditAgent.log(
            ticket_id=ticket_id,
            agent_name="IntakeAgent",
            event_type="ticket_ingested" if action == "inserted" else "ticket_updated",
            details={"source": source, "external_id": external_id, "action": action}
        )

        log.info("IntakeAgent finished", ticket_id=ticket_id, action=action)
        return ticket
