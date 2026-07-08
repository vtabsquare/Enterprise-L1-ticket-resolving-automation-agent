"""
policy_engine.py — Pre-execution policy validation gate.

Responsibilities:
  - Receives a ResolutionPlan
  - For each PlannedAction, checks against the policies table:
      * Is this action type allowed for this category?
      * Does the risk level exceed POLICY_MAX_AUTO_RISK?
      * Is the category in the blocked list?
      * Are any per-action conditions violated?
  - Returns a PolicyValidationResult with a per-action PolicyDecision
  - Emits POLICY_CHECKED audit event
  - The Tool Execution Agent MUST NOT run until this returns all_approved=True

CORE PRINCIPLE:
  This is the mandatory gate between the LLM's plan and real execution.
  It cannot be bypassed. Every action must be individually approved.

Full implementation in Phase 4.
"""

import structlog
from app.models import ResolutionPlan, PolicyValidationResult

log = structlog.get_logger(__name__)


class PolicyEngine:
    """Stub — implemented in Phase 4."""

    async def validate(self, plan: ResolutionPlan) -> PolicyValidationResult:
        log.info("PolicyEngine.validate called (stub)", ticket_id=str(plan.ticket_id))
        raise NotImplementedError("PolicyEngine is implemented in Phase 4")
