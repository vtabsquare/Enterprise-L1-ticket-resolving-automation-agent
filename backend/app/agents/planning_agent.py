"""
planning_agent.py — Generates a structured ActionPlan for a ticket using Gemini.

The agent:
1. Fetches ticket + classification + KB context
2. Calls gemini_service.generate_plan
3. Validates the JSON response against the ActionPlan Pydantic schema
4. Retries once if initial validation fails (Gemini occasionally returns slightly malformed JSON)
5. Falls back to an 'escalate' plan if both attempts fail

The output of this agent is an ActionPlan.
It is NOT allowed to call ToolExecutionAgent directly.
All ActionPlans must pass through policy_engine.evaluate() first.
"""

import json
import structlog
from typing import Any

from pydantic import ValidationError

from app.services import supabase_service
from app.services.gemini_service import get_gemini_service
from app.agents.audit_agent import AuditAgent
from app.agents.agent_utils import retry_once, safe_call
from app.schemas.action_plan import ActionPlan

log = structlog.get_logger(__name__)

# Fallback plan returned when both Gemini attempts fail to parse
_ESCALATE_FALLBACK = {
    "action_type": "escalate",
    "target_system": "jira",
    "parameters": {},
    "confidence": 0.0,
    "reasoning": "PlanningAgent failed to generate a valid plan after retry. Escalating for manual review.",
}

# Maps action_type -> target_system when Gemini doesn't specify
_ACTION_SYSTEM_MAP = {
    "password_reset": "ad",
    "ad_unlock":      "ad",
    "group_add":      "graph",
    "check_group_membership": "graph",
    "send_email":     "email",
    "create_ticket":  "jira",
    "escalate":       "jira",
    "close_ticket":   "jira",
}


def _gemini_response_to_action_plan(
    raw: dict[str, Any],
    fallback_confidence: float = 0.0,
) -> ActionPlan:
    """
    Maps the raw Gemini generate_plan output to the ActionPlan schema.

    Gemini returns:
      {proposed_action, action_payload, risk_level, reasoning}

    ActionPlan expects:
      {action_type, target_system, parameters, confidence, reasoning}

    proposed_action → action_type
    action_payload  → parameters
    target_system   is inferred from action_type if not present
    confidence      inherits from classification confidence (Gemini plan output doesn't include it)
    """
    action_type   = (raw.get("proposed_action") or raw.get("action_type", "escalate")).strip().lower()
    parameters    = raw.get("action_payload") or raw.get("parameters", {})
    reasoning     = raw.get("reasoning", "")
    # Extract target_system from the LLM directly, falling back to the map if omitted
    target_system = (raw.get("target_system") or _ACTION_SYSTEM_MAP.get(action_type, "jira")).strip().lower()

    # Extract plan_confidence from the LLM directly, falling back to classification confidence
    confidence = float(raw.get("plan_confidence") or raw.get("confidence", fallback_confidence))

    return ActionPlan(
        action_type=action_type,
        target_system=target_system,
        parameters=parameters if isinstance(parameters, dict) else {},
        confidence=confidence,
        reasoning=reasoning,
    )


def _attempt_plan(
    gemini,
    ticket: dict[str, Any],
    classification: dict[str, Any],
    kb_context: list[dict[str, Any]],
    attempt: int,
    fallback_confidence: float,
) -> ActionPlan | None:
    """Calls Gemini and tries to parse + validate the response. Returns None on any failure."""
    try:
        raw = gemini.generate_plan(ticket, classification, kb_context)
        plan = _gemini_response_to_action_plan(raw, fallback_confidence=fallback_confidence)
        log.info(
            "PlanningAgent plan validated",
            attempt=attempt,
            action_type=plan.action_type,
            confidence=plan.confidence,
        )
        return plan
    except (ValidationError, ValueError, KeyError, TypeError) as e:
        log.warning(
            "PlanningAgent plan validation failed",
            attempt=attempt,
            error=str(e),
            error_type=type(e).__name__,
            raw_response=raw,
        )
        return None
    except Exception as e:
        log.error("PlanningAgent unexpected error", attempt=attempt, error=str(e))
        return None


class PlanningAgent:
    @staticmethod
    def process(
        ticket_id: str,
        classification: dict[str, Any],
        kb_context: list[dict[str, Any]],
    ) -> ActionPlan:
        """
        Generates an ActionPlan for the given ticket.

        Args:
            ticket_id:      UUID of the ticket.
            classification: Output of ClassificationAgent.process().
            kb_context:     Output of KnowledgeAgent.retrieve_context().

        Returns:
            A validated ActionPlan instance.
            Falls back to an escalation plan if Gemini fails twice.
        """
        log.info("PlanningAgent starting", ticket_id=ticket_id)

        ticket = retry_once(
            lambda: supabase_service.get_ticket_by_id(ticket_id),
            agent="PlanningAgent", ticket_id=ticket_id, call="Supabase get_ticket_by_id",
        )
        if not ticket:
            raise ValueError(f"Ticket {ticket_id} not found")

        gemini = get_gemini_service()
        fallback_confidence = float(classification.get("confidence", 0.0))

        # ── Attempt 1 ─────────────────────────────────────────────────────────
        action_plan = _attempt_plan(gemini, ticket, classification, kb_context, 1, fallback_confidence)

        # ── Attempt 2 ─────────────────────────────────────────────────────────
        if action_plan is None:
            log.warning("PlanningAgent retrying plan generation (Attempt 2)", ticket_id=ticket_id)
            action_plan = _attempt_plan(gemini, ticket, classification, kb_context, 2, fallback_confidence)

        # ── Attempt 3 ─────────────────────────────────────────────────────────
        if action_plan is None:
            log.warning("PlanningAgent retrying plan generation (Attempt 3)", ticket_id=ticket_id)
            action_plan = _attempt_plan(gemini, ticket, classification, kb_context, 3, fallback_confidence)

        # ── Fallback ──────────────────────────────────────────────────────────
        if action_plan is None:
            log.error("PlanningAgent failed all 3 attempts, using escalation fallback", ticket_id=ticket_id)
            action_plan = ActionPlan(**_ESCALATE_FALLBACK)

        # Log agent action
        safe_call(
            lambda: supabase_service.insert_agent_action({
                "ticket_id": ticket_id,
                "agent_name": "PlanningAgent",
                "action_type": "generate_plan",
                "payload": action_plan.model_dump(),
                "status": "success",
            }),
            agent="PlanningAgent", ticket_id=ticket_id,
            call="Supabase insert_agent_action",
        )

        # Immutable audit log
        AuditAgent.log(
            ticket_id=ticket_id,
            agent_name="PlanningAgent",
            event_type="plan_generated",
            details={
                "action_type": action_plan.action_type,
                "target_system": action_plan.target_system,
                "confidence": action_plan.confidence,
            }
        )

        log.info(
            "PlanningAgent finished",
            ticket_id=ticket_id,
            action_type=action_plan.action_type,
            confidence=action_plan.confidence,
        )
        return action_plan
