"""
policy_engine.py — The ONLY gate between PlanningAgent and ToolExecutionAgent.

This module implements all safety checks. Every ActionPlan produced by PlanningAgent
MUST pass through evaluate() before any tool is allowed to execute. The Orchestrator
(Phase 5) enforces this — ToolExecutionAgent is never called directly.

Checks performed (in order):
  1. Confidence gate        — if plan.confidence < CONFIDENCE_THRESHOLD → escalate
  2. Policy lookup          — if no policy for action_type → block
  3. Action whitelist       — verify action_type matches policy.action_type
  4. allow_auto flag        — if policy.allow_auto is False → escalate
  5. Risk score gate        — risk_score = policy.risk_level × ticket.priority → escalate if > threshold
  6. Working hours check    — if outside configured window → escalate (queue)

Returns a PolicyDecision (approved | blocked | escalated).
"""

import structlog
from datetime import datetime, time
from zoneinfo import ZoneInfo
from functools import lru_cache
from typing import Any

from app.config import get_settings
from app.services import supabase_service
from app.agents.audit_agent import AuditAgent
from app.schemas.action_plan import ActionPlan, PolicyDecision, PolicyOutcome

log = structlog.get_logger(__name__)

# ── Risk score tables ─────────────────────────────────────────────────────────

_PRIORITY_SCORE: dict[str, int] = {
    "low":      1,
    "medium":   2,
    "high":     3,
    "critical": 4,
}

_RISK_SCORE: dict[str, int] = {
    "low":    1,
    "medium": 2,
    "high":   3,
}

# Risk score = policy_risk × ticket_priority.
# Max possible = 3 × 4 = 12. Escalate if above this threshold.
_RISK_SCORE_THRESHOLD = 4   # e.g. medium-risk + high-priority (2×3=6 > 4) → escalate

# Confidence below this always forces escalation regardless of policy
_CONFIDENCE_THRESHOLD = 0.75


def _get_working_hours_config() -> tuple[time, time, str]:
    """
    Returns (work_start, work_end, timezone_name) from config.
    Defaults to 09:00–18:00 Asia/Kolkata if not set.
    """
    settings = get_settings()
    tz_name = getattr(settings, "policy_timezone", "Asia/Kolkata")
    start_str = getattr(settings, "policy_work_start", "09:00")
    end_str   = getattr(settings, "policy_work_end",   "18:00")

    try:
        work_start = time.fromisoformat(start_str)
        work_end   = time.fromisoformat(end_str)
    except ValueError:
        log.warning("Invalid working hours config, using defaults", start=start_str, end=end_str)
        work_start = time(9, 0)
        work_end   = time(18, 0)

    return work_start, work_end, tz_name


def _is_within_working_hours() -> bool:
    """Returns True if current time falls within the configured working window."""
    work_start, work_end, tz_name = _get_working_hours_config()
    try:
        tz = ZoneInfo(tz_name)
    except Exception:
        tz = ZoneInfo("UTC")

    now_local = datetime.now(tz).time()
    return work_start <= now_local <= work_end


def _get_escalation_target(ticket: dict[str, Any]) -> str:
    """
    Looks up the resolver group for the ticket's category to find an escalation email.
    Falls back to a generic L2 queue.
    """
    category = ticket.get("category", "unknown")
    try:
        client = supabase_service.get_supabase_client()
        resp = supabase_service.get_supabase_client().table("resolver_groups").select(
            "escalation_email"
        ).eq("category", category).execute()
        if resp.data:
            return resp.data[0].get("escalation_email", "it-helpdesk@corp.example.com")
    except Exception as e:
        log.warning("Failed to fetch escalation target", error=str(e))
    return "it-helpdesk@corp.example.com"


def evaluate(
    action_plan: ActionPlan,
    ticket: dict[str, Any],
) -> PolicyDecision:
    """
    Evaluate an ActionPlan against all policy rules.

    Args:
        action_plan: The plan produced by PlanningAgent.
        ticket:      The full ticket dict from the database.

    Returns:
        PolicyDecision with outcome = approved | blocked | escalated.
    """
    ticket_id = ticket.get("id")

    def _escalate(reason: str, policy_id: str | None = None) -> PolicyDecision:
        target = _get_escalation_target(ticket)
        log.info("PolicyEngine → ESCALATED", reason=reason, ticket_id=ticket_id)
        _write_audit(ticket_id, action_plan, "escalated", reason)
        return PolicyDecision(
            outcome=PolicyOutcome.ESCALATED,
            reason=reason,
            policy_id=policy_id,
            action_plan=action_plan,
            escalation_target=target,
        )

    def _block(reason: str) -> PolicyDecision:
        log.info("PolicyEngine → BLOCKED", reason=reason, ticket_id=ticket_id)
        _write_audit(ticket_id, action_plan, "blocked", reason)
        return PolicyDecision(
            outcome=PolicyOutcome.BLOCKED,
            reason=reason,
            policy_id=None,
            action_plan=action_plan,
        )

    def _approve(policy_id: str) -> PolicyDecision:
        reason = "All policy checks passed."
        log.info("PolicyEngine → APPROVED", ticket_id=ticket_id, action_type=action_plan.action_type)
        _write_audit(ticket_id, action_plan, "approved", reason)
        return PolicyDecision(
            outcome=PolicyOutcome.APPROVED,
            reason=reason,
            policy_id=policy_id,
            action_plan=action_plan,
        )

    log.info(
        "PolicyEngine evaluating",
        ticket_id=ticket_id,
        action_type=action_plan.action_type,
        confidence=action_plan.confidence,
    )

    # ── Check 0: Explicit Escalate Action ──────────────────────────────────────
    if action_plan.action_type == "escalate":
        return _escalate(
            "Plan explicitly requested escalation.",
            policy_id=None
        )

    # ── Check 1: Confidence gate ───────────────────────────────────────────────
    classification_confidence = float(ticket.get("confidence") or 0.0)
    plan_confidence = float(action_plan.confidence)
    effective_confidence = min(classification_confidence, plan_confidence)

    if effective_confidence < _CONFIDENCE_THRESHOLD:
        return _escalate(
            f"Effective confidence {effective_confidence:.2f} "
            f"(classification={classification_confidence:.2f}, plan={plan_confidence:.2f}) "
            f"is below the required threshold of {_CONFIDENCE_THRESHOLD}. Manual review required."
        )

    # ── Check 2: Policy lookup ─────────────────────────────────────────────────
    policy = _fetch_policy(action_plan.action_type, ticket.get("category"))
    if policy is None:
        return _escalate(
            f"No policy found for action_type='{action_plan.action_type}' "
            f"in category='{ticket.get('category')}'. Action is plausible but unauthorized. "
            f"Routing to human for manual review."
        )

    policy_id = str(policy.get("id"))

    # ── Check 3: allow_auto flag ───────────────────────────────────────────────
    if not policy.get("allow_auto", False):
        return _escalate(
            f"Policy '{policy.get('policy_name')}' requires manual approval "
            f"(allow_auto=false).",
            policy_id=policy_id,
        )

    # ── Check 4: Risk score gate ───────────────────────────────────────────────
    ticket_priority = ticket.get("priority", "medium")
    policy_risk     = policy.get("risk_level", "medium")
    
    # HARD FLOOR: High-risk actions always require human review, regardless of priority urgency
    if policy_risk == "high":
        return _escalate(
            f"Action is classified as HIGH RISK. Escalating for safety regardless of "
            f"ticket priority ({ticket_priority}).",
            policy_id=policy_id,
        )
        
    risk_score = _RISK_SCORE.get(policy_risk, 2) * _PRIORITY_SCORE.get(ticket_priority, 2)

    if risk_score > _RISK_SCORE_THRESHOLD:
        return _escalate(
            f"Risk score {risk_score} exceeds threshold {_RISK_SCORE_THRESHOLD} "
            f"(policy_risk={policy_risk}, ticket_priority={ticket_priority}). Escalating for safety.",
            policy_id=policy_id,
        )

    # ── Check 5: Target System Whitelist ───────────────────────────────────────
    conditions = policy.get("conditions") or {}
    allowed_systems = conditions.get("allowed_systems")
    if allowed_systems is not None:
        if not isinstance(allowed_systems, list):
            allowed_systems = [allowed_systems]
        if action_plan.target_system not in allowed_systems:
            return _block(
                f"Target system '{action_plan.target_system}' is not permitted for action "
                f"'{action_plan.action_type}'. Allowed systems: {allowed_systems}."
            )

    # ── Check 6: Working hours ─────────────────────────────────────────────────
    if conditions.get("business_hours_only", False) and not _is_within_working_hours():
        work_start, work_end, tz_name = _get_working_hours_config()
        return _escalate(
            f"Policy requires action to run during business hours "
            f"({work_start.strftime('%H:%M')}–{work_end.strftime('%H:%M')} {tz_name}). "
            f"Ticket queued for next business window.",
            policy_id=policy_id,
        )

    # ── Check 7: Required Parameters Validation ────────────────────────────────
    if action_plan.action_type == "dl_update":
        user_email = action_plan.parameters.get("user_email", "").strip()
        list_email = action_plan.parameters.get("list_email", "").strip()
        
        if not user_email:
            return _escalate(
                "Missing 'user_email' parameter for dl_update. The target user could not be resolved from the ticket.",
                policy_id=policy_id
            )
        if not list_email:
            return _escalate(
                "Missing 'list_email' parameter for dl_update. The target distribution list could not be resolved from the ticket.",
                policy_id=policy_id
            )

    # ── All checks passed ──────────────────────────────────────────────────────
    return _approve(policy_id)


def _fetch_policy(action_type: str, category: str | None) -> dict[str, Any] | None:
    """
    Fetches the best-matching policy for the given action_type and category.
    Prefers an exact action_type match, then falls back to action_type='any' for the category.
    """
    try:
        client = supabase_service.get_supabase_client()

        # Exact match first — must match both action_type AND category
        resp = client.table("policies").select("*").eq("action_type", action_type).execute()
        if resp.data:
            for p in resp.data:
                if p.get("category") == category:
                    return p
            # If we didn't find a matching category, DO NOT return resp.data[0]
            # Fall through to the 'any' action check below.

        # Fallback: 'any' action for this category
        if category:
            resp2 = client.table("policies").select("*").eq("category", category).eq("action_type", "any").execute()
            if resp2.data:
                return resp2.data[0]

    except Exception as e:
        log.error("PolicyEngine failed to fetch policy", error=str(e), action_type=action_type)

    return None


def _write_audit(
    ticket_id: str | None,
    action_plan: ActionPlan,
    outcome: str,
    reason: str,
) -> None:
    """Write the policy decision to the audit log."""
    try:
        AuditAgent.log(
            ticket_id=ticket_id,
            agent_name="PolicyEngine",
            event_type="policy_checked",
            details={
                "outcome": outcome,
                "reason": reason,
                "action_type": action_plan.action_type,
                "confidence": action_plan.confidence,
            }
        )
    except Exception as e:
        log.error("PolicyEngine audit write failed", error=str(e))
