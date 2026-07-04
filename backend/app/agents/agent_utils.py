"""
agent_utils.py — Shared utilities for all orchestrator agents.

Provides safe_call(), a helper for best-effort external system calls that should
never crash the orchestrator pipeline on failure. Core/critical calls (e.g.
get_ticket_by_id) intentionally do NOT use this — they should raise.
"""

import structlog
from typing import Callable, TypeVar

log = structlog.get_logger(__name__)

T = TypeVar("T")


def safe_call(
    fn: Callable[[], T],
    *,
    agent: str,
    ticket_id: str | None,
    call: str,
    default: T | None = None,
) -> T | None:
    """
    Execute fn() as a best-effort external system call.

    On success, returns fn()'s return value.
    On any exception, logs a structured warning (with agent, ticket_id, call
    description, and error message) and returns `default` (None by default).

    Use this for:
      - ITSM comment/close writes (Jira, ServiceNow)
      - DB audit/logging writes (insert_agent_action, update_ticket)
      - Graph API notification calls in TicketUpdateAgent / EscalationAgent

    Do NOT use this for:
      - get_ticket_by_id() — if the ticket doesn't exist, there is no safe
        recovery. This should raise and let the Orchestrator's top-level catch
        handle it.
      - Core tool execution calls (_attempt() in ToolExecutionAgent) — these
        have their own retry loop and structured ExecutionResult return type.
    """
    try:
        return fn()
    except Exception as e:
        log.warning(
            "External call failed — continuing",
            agent=agent,
            ticket_id=ticket_id,
            call=call,
            error=str(e),
        )
        return default
