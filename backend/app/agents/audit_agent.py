"""
audit_agent.py — Audit trail logger.

Provides an immutable logging interface for all agent actions and system events.
"""

import structlog
from typing import Any

from app.services import supabase_service

log = structlog.get_logger(__name__)


class AuditAgent:
    @staticmethod
    def log(
        ticket_id: str | None,
        agent_name: str,
        event_type: str,
        details: dict[str, Any],
        user_id: str | None = None
    ) -> None:
        """
        Write an immutable event to the audit_logs table.
        """
        payload = {
            "ticket_id": ticket_id,
            "agent_name": agent_name,
            "event_type": event_type,
            "details": details,
            "user_id": user_id,
        }
        
        try:
            supabase_service.insert_audit_log(payload)
            log.info("Audit log written", audit_event=event_type, agent=agent_name, ticket_id=ticket_id)
        except Exception as e:
            # Audit log failures shouldn't necessarily crash the whole pipeline,
            # but they should be loudly monitored.
            log.error("Failed to write audit log", error=str(e), payload=payload)
