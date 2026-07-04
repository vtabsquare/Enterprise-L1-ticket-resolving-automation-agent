"""
schemas/action_plan.py — Pydantic schemas for the Planning Agent and Policy Engine.

These are the ONLY typed contracts between:
  PlanningAgent → PolicyEngine → ToolExecutionAgent

Nothing proceeds to execution without passing through PolicyDecision.
"""

from enum import Enum
from typing import Any, Literal
from pydantic import BaseModel, Field, field_validator


# ── ActionPlan — output of PlanningAgent ──────────────────────────────────────

class ActionPlan(BaseModel):
    """
    The structured plan produced by PlanningAgent after calling Gemini.
    Must pass PolicyEngine validation before any tool may be executed.
    """
    action_type: Literal["password_reset", "ad_unlock", "group_add", "send_email", "escalate", "dl_update"] = Field(
        ...,
        description="The specific action to execute. Must be one of the strictly supported tool names."
    )
    target_system: str = Field(
        ...,
        description="The system the action targets. e.g. 'ad', 'jira', 'graph', 'servicenow', 'email'"
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict,
        description="Action-specific parameters. e.g. {user_email: '...', group_name: '...'}"
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="Gemini's confidence that this plan is correct. Below 0.75 forces escalation."
    )
    reasoning: str = Field(
        ...,
        description="Gemini's step-by-step reasoning for producing this plan."
    )

    @field_validator("action_type")
    @classmethod
    def action_type_not_empty(cls, v: str) -> str:
        # Pydantic Literal validation happens first, but keeping strip/lower just in case
        if not v.strip():
            raise ValueError("action_type must not be empty")
        return v.strip().lower()

    @field_validator("target_system")
    @classmethod
    def target_system_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("target_system must not be empty")
        return v.strip().lower()


# ── PolicyDecision — output of PolicyEngine ───────────────────────────────────

class PolicyOutcome(str, Enum):
    APPROVED  = "approved"
    BLOCKED   = "blocked"
    ESCALATED = "escalated"


class PolicyDecision(BaseModel):
    """
    The decision returned by PolicyEngine.

    This is the ONLY gate between PlanningAgent and ToolExecutionAgent.
    ToolExecutionAgent MUST NOT be called unless decision == APPROVED.
    """
    outcome: PolicyOutcome = Field(
        ...,
        description="approved | blocked | escalated"
    )
    reason: str = Field(
        ...,
        description="Human-readable explanation of the decision. Written to audit_logs."
    )
    policy_id: str | None = Field(
        default=None,
        description="UUID of the matched policy row, if one was found."
    )
    action_plan: ActionPlan = Field(
        ...,
        description="The ActionPlan this decision applies to."
    )
    escalation_target: str | None = Field(
        default=None,
        description="Email or queue to escalate to, populated when outcome == ESCALATED."
    )

    @property
    def is_approved(self) -> bool:
        return self.outcome == PolicyOutcome.APPROVED

    @property
    def is_escalated(self) -> bool:
        return self.outcome == PolicyOutcome.ESCALATED

    @property
    def is_blocked(self) -> bool:
        return self.outcome == PolicyOutcome.BLOCKED
