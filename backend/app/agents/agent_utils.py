"""
agent_utils.py — Shared utilities for all orchestrator agents.

Provides helpers for external system calls:
- safe_call() for best-effort calls that should not crash the pipeline.
- retry_once() for critical Supabase calls that should retry transient failures
  once and then raise if the retry also fails.
"""

import time
import structlog
from typing import Callable, TypeVar

log = structlog.get_logger(__name__)

T = TypeVar("T")


def retry_once(
    fn: Callable[[], T],
    *,
    ticket_id: str | None,
    call: str,
    agent: str | None = None,
    delay_seconds: float = 2.0,
) -> T:
    """
    Execute fn(); on any exception wait briefly and retry once.

    Use this for critical Supabase operations where a transient socket failure
    should not immediately force escalation, but a repeated failure should still
    raise so the caller's normal failure path runs.
    """
    try:
        return fn()
    except Exception as e:
        log.warning(
            "External call failed - retrying once",
            agent=agent,
            ticket_id=ticket_id,
            call=call,
            error=str(e),
        )
        time.sleep(delay_seconds)
        return fn()


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
      - DB audit/logging writes (insert_agent_action)
      - Graph API notification calls in TicketUpdateAgent / EscalationAgent

    Do NOT use this for:
      - Critical Supabase reads/writes that determine pipeline control flow.
        Use retry_once() so transient failures get one retry, then still raise.
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
