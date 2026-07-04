"""
itsm_client.py — Abstract base class for all ITSM integrations.

Every ITSM integration (Jira, ServiceNow, or any future system) MUST
implement this interface. No agent, router, or service outside of
jira_service.py and servicenow_service.py is allowed to reference
Jira-specific or ServiceNow-specific types or APIs.

Methods:
    fetch_ticket(external_id)              → normalized dict
    create_comment(external_id, text)      → None
    update_status(external_id, status)     → None
    close_ticket(external_id)              → None
    parse_webhook_payload(payload)         → normalized dict
"""

from abc import ABC, abstractmethod
from typing import Any


# ── Normalized ticket dict shape ──────────────────────────────────────────────
# Both JiraClient and MockServiceNowClient return this exact shape.
# The rest of the pipeline ONLY ever sees this — never raw Jira/SN fields.
#
# {
#     "external_id":    str,   # e.g. "KAN-42" or "SN-001"
#     "source":         str,   # "jira" | "servicenow"
#     "summary":        str,
#     "description":    str | None,
#     "status":         str,   # normalised: "open" | "in_progress" | "resolved" | "closed"
#     "priority":       str,   # normalised: "low" | "medium" | "high" | "critical"
#     "reporter_email": str | None,
#     "raw":            dict,  # full original payload preserved for debugging
# }


class ITSMClient(ABC):
    """
    Abstract base class for ITSM integrations.

    Implementations:
        JiraClient          — backend/app/services/jira_service.py   (real)
        MockServiceNowClient — backend/app/services/servicenow_service.py (mock)
        ServiceNowClient    — backend/app/services/servicenow_service.py (future real)
    """

    @abstractmethod
    def fetch_ticket(self, external_id: str) -> dict[str, Any]:
        """
        Retrieve a single ticket by its external ID and return a normalized dict.

        Args:
            external_id: Jira issue key (e.g. "KAN-42") or ServiceNow sys_id.

        Returns:
            Normalized ticket dict (see shape above).

        Raises:
            ITSMTicketNotFoundError: if the ticket does not exist.
            ITSMConnectionError:     on network or auth failure.
        """
        ...

    @abstractmethod
    def create_comment(self, external_id: str, text: str) -> None:
        """
        Post a comment to a ticket in the ITSM system.

        Args:
            external_id: The ticket to comment on.
            text:        Plain-text comment body.
        """
        ...

    @abstractmethod
    def update_status(self, external_id: str, status: str) -> None:
        """
        Update the status/state of a ticket in the ITSM system.

        Args:
            external_id: The ticket to update.
            status:      Normalised status string — implementation maps to
                         system-specific values internally.
                         Accepted values: "open" | "in_progress" | "resolved" | "closed"
        """
        ...

    @abstractmethod
    def close_ticket(self, external_id: str) -> None:
        """
        Mark a ticket as resolved/closed in the ITSM system.

        Args:
            external_id: The ticket to close.
        """
        ...

    @abstractmethod
    def parse_webhook_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Parse a raw inbound webhook payload from this ITSM system and return
        a normalized ticket dict (same shape as fetch_ticket returns).

        This is the ONLY place where raw Jira/ServiceNow webhook field names
        are referenced — nothing outside the client implementation sees them.

        Args:
            payload: The raw JSON body received from the webhook.

        Returns:
            Normalized ticket dict.

        Raises:
            ITSMValidationError: if the payload is malformed or missing required fields.
        """
        ...


# ── Custom exceptions ─────────────────────────────────────────────────────────

class ITSMError(Exception):
    """Base exception for all ITSM client errors."""


class ITSMTicketNotFoundError(ITSMError):
    """Raised when a ticket ID does not exist in the ITSM system."""


class ITSMConnectionError(ITSMError):
    """Raised when the ITSM system is unreachable or returns auth errors."""


class ITSMValidationError(ITSMError):
    """Raised when a payload is malformed or a field update is rejected."""
