"""
models.py — Pydantic v2 schemas for every data object in the platform.

Mirrors the Supabase schema exactly. These models are used for:
  - API request/response validation
  - Inter-agent message passing
  - Serialisation to/from the database

Tables covered:
  tickets, agent_actions, knowledge_base, policies,
  resolver_groups, escalations, audit_logs
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, model_validator


# ─────────────────────────────────────────────────────────────────────────────
# Shared enums
# ─────────────────────────────────────────────────────────────────────────────

class TicketSource(str, Enum):
    JIRA = "jira"
    SERVICENOW = "servicenow"


class TicketStatus(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    ESCALATED = "escalated"
    CLOSED = "closed"


class TicketPriority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TicketCategory(str, Enum):
    PASSWORD_RESET = "password_reset"
    ACCOUNT_UNLOCK = "account_unlock"
    SOFTWARE_ACCESS = "software_access"
    HARDWARE_ISSUE = "hardware_issue"
    NETWORK_CONNECTIVITY = "network_connectivity"
    VPN_ACCESS = "vpn_access"
    EMAIL_ISSUE = "email_issue"
    ONBOARDING = "onboarding"
    OFFBOARDING = "offboarding"
    GENERAL_IT = "general_it"
    UNKNOWN = "unknown"


class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class ActionStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    BLOCKED = "blocked"
    EXECUTING = "executing"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class EventType(str, Enum):
    TICKET_INGESTED = "ticket_ingested"
    TICKET_CLASSIFIED = "ticket_classified"
    KB_RETRIEVED = "kb_retrieved"
    PLAN_GENERATED = "plan_generated"
    POLICY_CHECKED = "policy_checked"
    ACTION_EXECUTED = "action_executed"
    TICKET_UPDATED = "ticket_updated"
    TICKET_ESCALATED = "ticket_escalated"
    TICKET_CLOSED = "ticket_closed"
    ERROR = "error"


# ─────────────────────────────────────────────────────────────────────────────
# tickets
# ─────────────────────────────────────────────────────────────────────────────

class TicketBase(BaseModel):
    source: TicketSource
    external_id: str                         # Jira issue key or SN sys_id
    summary: str
    description: Optional[str] = None
    category: TicketCategory = TicketCategory.UNKNOWN
    priority: TicketPriority = TicketPriority.MEDIUM
    status: TicketStatus = TicketStatus.OPEN
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class TicketCreate(TicketBase):
    pass


class TicketUpdate(BaseModel):
    category: Optional[TicketCategory] = None
    priority: Optional[TicketPriority] = None
    status: Optional[TicketStatus] = None
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)


class Ticket(TicketBase):
    id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# agent_actions
# ─────────────────────────────────────────────────────────────────────────────

class AgentActionBase(BaseModel):
    ticket_id: uuid.UUID
    agent_name: str
    action_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    result: Optional[dict[str, Any]] = None
    status: ActionStatus = ActionStatus.PENDING


class AgentActionCreate(AgentActionBase):
    pass


class AgentAction(AgentActionBase):
    id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# knowledge_base
# ─────────────────────────────────────────────────────────────────────────────

class KnowledgeArticleBase(BaseModel):
    title: str
    content: str
    category: TicketCategory
    source: str = "manual"
    # embedding is stored in DB but not exposed in standard API responses
    # it is handled internally by the knowledge agent


class KnowledgeArticleCreate(KnowledgeArticleBase):
    pass


class KnowledgeArticle(KnowledgeArticleBase):
    id: uuid.UUID
    created_at: datetime

    model_config = {"from_attributes": True}


class KnowledgeArticleWithScore(KnowledgeArticle):
    """Returned by RAG retrieval — includes cosine similarity score."""
    similarity_score: float = Field(ge=0.0, le=1.0)


# ─────────────────────────────────────────────────────────────────────────────
# policies
# ─────────────────────────────────────────────────────────────────────────────

class PolicyBase(BaseModel):
    policy_name: str
    category: TicketCategory
    action_type: str
    risk_level: RiskLevel
    allow_auto: bool
    conditions: dict[str, Any] = Field(default_factory=dict)


class PolicyCreate(PolicyBase):
    pass


class Policy(PolicyBase):
    id: uuid.UUID

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# resolver_groups
# ─────────────────────────────────────────────────────────────────────────────

class ResolverGroupBase(BaseModel):
    group_name: str
    category: TicketCategory
    jira_queue: Optional[str] = None
    servicenow_group: Optional[str] = None
    escalation_email: Optional[str] = None


class ResolverGroupCreate(ResolverGroupBase):
    pass


class ResolverGroup(ResolverGroupBase):
    id: uuid.UUID

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# escalations
# ─────────────────────────────────────────────────────────────────────────────

class EscalationBase(BaseModel):
    ticket_id: uuid.UUID
    reason: str
    escalated_to: str                        # email or group name
    notified_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None


class EscalationCreate(EscalationBase):
    pass


class Escalation(EscalationBase):
    id: uuid.UUID

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# audit_logs
# ─────────────────────────────────────────────────────────────────────────────

class AuditLogBase(BaseModel):
    ticket_id: Optional[uuid.UUID] = None
    agent_name: str
    event_type: EventType
    details: dict[str, Any] = Field(default_factory=dict)
    user_id: Optional[str] = None            # human user if action was manual


class AuditLogCreate(AuditLogBase):
    pass


class AuditLog(AuditLogBase):
    id: uuid.UUID
    timestamp: datetime

    model_config = {"from_attributes": True}


# ─────────────────────────────────────────────────────────────────────────────
# Inter-agent message types (not stored in DB — used for pipeline data flow)
# ─────────────────────────────────────────────────────────────────────────────

class RawTicketPayload(BaseModel):
    """
    Normalised ticket payload produced by the Intake Agent.
    Source-agnostic — both Jira and ServiceNow webhooks map to this.
    """
    source: TicketSource
    external_id: str
    summary: str
    description: Optional[str] = None
    raw_payload: dict[str, Any] = Field(default_factory=dict)


class ClassificationResult(BaseModel):
    """Output of the Classification Agent."""
    category: TicketCategory
    priority: TicketPriority
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str


class PlannedAction(BaseModel):
    """A single executable step within a resolution plan."""
    step: int
    action_type: str                         # e.g. "ad_unlock", "password_reset"
    target: str                              # e.g. username, email, device
    parameters: dict[str, Any] = Field(default_factory=dict)
    requires_approval: bool = False
    risk_level: RiskLevel = RiskLevel.LOW


class ResolutionPlan(BaseModel):
    """Full structured plan produced by the Planning Agent."""
    ticket_id: uuid.UUID
    reasoning: str
    actions: list[PlannedAction]
    estimated_resolution: str
    requires_human_review: bool = False

    @model_validator(mode="after")
    def actions_must_be_ordered(self) -> "ResolutionPlan":
        for i, action in enumerate(self.actions, start=1):
            if action.step != i:
                raise ValueError(f"Action steps must be sequential; expected {i}, got {action.step}")
        return self


class PolicyDecision(BaseModel):
    """Output of the Policy Engine for a single planned action."""
    action: PlannedAction
    approved: bool
    reason: str
    policy_id: Optional[uuid.UUID] = None


class PolicyValidationResult(BaseModel):
    """Aggregate policy result for a full resolution plan."""
    ticket_id: uuid.UUID
    all_approved: bool
    decisions: list[PolicyDecision]
    blocked_actions: list[PlannedAction] = Field(default_factory=list)


# ─────────────────────────────────────────────────────────────────────────────
# API response wrappers
# ─────────────────────────────────────────────────────────────────────────────

class HealthResponse(BaseModel):
    status: str
    database: bool
    redis: bool
    version: str


class PaginatedResponse(BaseModel):
    """Generic paginated list wrapper."""
    items: list[Any]
    total: int
    page: int
    page_size: int
    has_next: bool

    @model_validator(mode="after")
    def compute_has_next(self) -> "PaginatedResponse":
        self.has_next = (self.page * self.page_size) < self.total
        return self
