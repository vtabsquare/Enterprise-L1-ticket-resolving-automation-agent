"""
servicenow_service.py — MockServiceNowClient (active) + ServiceNowClient (future).

ACTIVE NOW:  MockServiceNowClient(ITSMClient)
  - Returns realistic ServiceNow Table API shaped data
  - Logs exactly what the real API call WOULD have been (method + endpoint)
  - Never makes a real HTTP request
  - In-memory state mutates on update/close so the full pipeline tests correctly

FUTURE:      ServiceNowClient(ITSMClient)
  - Real REST Table API calls written and ready
  - Commented out with "# enable once SERVICENOW_URL credentials are available"
  - Swap by changing SERVICENOW_MODE=real in .env and uncommenting the factory line

All ServiceNow-specific field names are confined to THIS FILE ONLY.
"""

import structlog
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from typing import Any

from app.config import get_settings
from app.services.itsm_client import (
    ITSMClient,
    ITSMTicketNotFoundError,
    ITSMConnectionError,
    ITSMValidationError,
)

log = structlog.get_logger(__name__)

# ── Priority / status maps (ServiceNow → normalised) ─────────────────────────
_SN_PRIORITY_MAP = {
    "1": "critical",
    "2": "high",
    "3": "medium",
    "4": "low",
    "5": "low",
}
_SN_STATE_MAP = {
    "1": "open",          # New
    "2": "in_progress",   # In Progress
    "3": "in_progress",   # On Hold
    "4": "resolved",      # Resolved
    "5": "closed",        # Closed
    "6": "closed",        # Cancelled
}
_NORMALISED_TO_SN_STATE = {
    "open":        "1",
    "in_progress": "2",
    "resolved":    "4",
    "closed":      "5",
}

# ── Realistic sample incident data (ServiceNow Table API response shape) ──────
_SAMPLE_INCIDENTS: list[dict[str, Any]] = [
    {
        "sys_id":            "abc123def456abc1",
        "number":            "INC0010001",
        "short_description": "Cannot log into VPN — getting authentication error",
        "description":       (
            "User jsmith reports being unable to connect to the corporate VPN since this morning. "
            "Error message: 'Authentication failed. Check your credentials.' "
            "Last successful connection was Friday afternoon. No recent password change."
        ),
        "state":             "1",
        "priority":          "2",
        "urgency":           "2",
        "impact":            "2",
        "caller_id":         {"value": "john.smith@corp.example.com", "display_value": "John Smith"},
        "assigned_to":       {"value": "", "display_value": ""},
        "sys_created_on":    (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%d %H:%M:%S"),
        "sys_updated_on":    (datetime.now(timezone.utc) - timedelta(minutes=45)).strftime("%Y-%m-%d %H:%M:%S"),
        "category":          "network",
        "subcategory":       "vpn",
        "close_notes":       "",
        "work_notes":        "",
        "comments":          "",
    },
    {
        "sys_id":            "bcd234efa567bcd2",
        "number":            "INC0010002",
        "short_description": "Password expired — need reset for user agarcia",
        "description":       (
            "HR manager requesting password reset for Ana Garcia (agarcia) "
            "who is locked out after her password expired. She is in the Mumbai office."
        ),
        "state":             "1",
        "priority":          "3",
        "urgency":           "3",
        "impact":            "3",
        "caller_id":         {"value": "hr.manager@corp.example.com", "display_value": "HR Manager"},
        "assigned_to":       {"value": "", "display_value": ""},
        "sys_created_on":    (datetime.now(timezone.utc) - timedelta(minutes=30)).strftime("%Y-%m-%d %H:%M:%S"),
        "sys_updated_on":    (datetime.now(timezone.utc) - timedelta(minutes=20)).strftime("%Y-%m-%d %H:%M:%S"),
        "category":          "user_management",
        "subcategory":       "password_reset",
        "close_notes":       "",
        "work_notes":        "",
        "comments":          "",
    },
    {
        "sys_id":            "cde345fab678cde3",
        "number":            "INC0010003",
        "short_description": "Request access to Confluence and Jira for new hire",
        "description":       (
            "New employee David Lee (dlee) starting Monday needs access to: "
            "Confluence (Engineering space), Jira (Engineering project), Slack. "
            "Manager: sarah.chen@corp.example.com"
        ),
        "state":             "1",
        "priority":          "4",
        "urgency":           "4",
        "impact":            "4",
        "caller_id":         {"value": "sarah.chen@corp.example.com", "display_value": "Sarah Chen"},
        "assigned_to":       {"value": "", "display_value": ""},
        "sys_created_on":    (datetime.now(timezone.utc) - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S"),
        "sys_updated_on":    (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
        "category":          "access",
        "subcategory":       "software_access",
        "close_notes":       "",
        "work_notes":        "",
        "comments":          "",
    },
    {
        "sys_id":            "def456abc789def4",
        "number":            "INC0010004",
        "short_description": "Laptop running very slow — possibly needs RAM upgrade",
        "description":       (
            "User mwilliams reports her laptop (Dell Latitude 7420, asset tag LAP-4821) "
            "has been extremely slow for the past week. RAM at 95% usage per diagnostics."
        ),
        "state":             "1",
        "priority":          "3",
        "urgency":           "3",
        "impact":            "2",
        "caller_id":         {"value": "m.williams@corp.example.com", "display_value": "Mary Williams"},
        "assigned_to":       {"value": "", "display_value": ""},
        "sys_created_on":    (datetime.now(timezone.utc) - timedelta(hours=5)).strftime("%Y-%m-%d %H:%M:%S"),
        "sys_updated_on":    (datetime.now(timezone.utc) - timedelta(hours=4)).strftime("%Y-%m-%d %H:%M:%S"),
        "category":          "hardware",
        "subcategory":       "laptop",
        "close_notes":       "",
        "work_notes":        "",
        "comments":          "",
    },
    {
        "sys_id":            "efa567bcd890efa5",
        "number":            "INC0010005",
        "short_description": "AD account locked — user cannot log in to workstation",
        "description":       (
            "Robert Kim (rkim) is locked out of his workstation account after "
            "multiple failed login attempts. New York office, badge ID NY-2291."
        ),
        "state":             "1",
        "priority":          "2",
        "urgency":           "2",
        "impact":            "2",
        "caller_id":         {"value": "rkim@corp.example.com", "display_value": "Robert Kim"},
        "assigned_to":       {"value": "", "display_value": ""},
        "sys_created_on":    (datetime.now(timezone.utc) - timedelta(minutes=15)).strftime("%Y-%m-%d %H:%M:%S"),
        "sys_updated_on":    (datetime.now(timezone.utc) - timedelta(minutes=10)).strftime("%Y-%m-%d %H:%M:%S"),
        "category":          "user_management",
        "subcategory":       "account_unlock",
        "close_notes":       "",
        "work_notes":        "",
        "comments":          "",
    },
]

# In-memory mutable store — simulates ServiceNow DB for mock purposes
_MOCK_DB: dict[str, dict[str, Any]] = {
    inc["sys_id"]: dict(inc) for inc in _SAMPLE_INCIDENTS
}


def _normalise_sn(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Maps a ServiceNow incident record to the source-agnostic normalized dict.
    This is the ONLY place ServiceNow field names are referenced.
    """
    caller = raw.get("caller_id") or {}
    caller_email = (
        caller.get("value", "") if isinstance(caller, dict) else str(caller)
    )
    return {
        "external_id":    raw.get("sys_id", raw.get("number", "")),
        "source":         "servicenow",
        "summary":        raw.get("short_description", ""),
        "description":    raw.get("description"),
        "status":         _SN_STATE_MAP.get(raw.get("state", "1"), "open"),
        "priority":       _SN_PRIORITY_MAP.get(raw.get("priority", "3"), "medium"),
        "reporter_email": caller_email or None,
        "raw":            raw,
    }


# ─────────────────────────────────────────────────────────────────────────────
# MockServiceNowClient — ACTIVE
# ─────────────────────────────────────────────────────────────────────────────

class MockServiceNowClient(ITSMClient):
    """
    Realistic mock of the ServiceNow REST Table API.

    Every method logs exactly what it WOULD have sent:
        METHOD https://{instance}.service-now.com/api/now/table/incident/...

    No real HTTP requests are ever made.
    State mutations (update_status, close_ticket, create_comment) persist
    in-memory so the full pipeline can be tested end-to-end.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = settings.servicenow_url
        log.info("MockServiceNowClient initialised", mode="MOCK", base_url=self._base_url)

    def _log_would_call(self, method: str, endpoint: str, body: Any = None) -> None:
        """Logs exactly what the real API call WOULD have been."""
        log.info(
            "[MOCK ServiceNow] Would call real API",
            method=method,
            endpoint=f"{self._base_url}{endpoint}",
            body=body,
        )

    def fetch_ticket(self, external_id: str) -> dict[str, Any]:
        self._log_would_call("GET", f"/api/now/table/incident/{external_id}")
        if external_id not in _MOCK_DB:
            raise ITSMTicketNotFoundError(
                f"[MOCK] ServiceNow incident not found: {external_id}"
            )
        result = _normalise_sn(_MOCK_DB[external_id])
        log.info("[MOCK ServiceNow] fetch_ticket OK", sys_id=external_id, summary=result["summary"])
        return result

    def create_comment(self, external_id: str, text: str) -> None:
        self._log_would_call(
            "PATCH",
            f"/api/now/table/incident/{external_id}",
            body={"comments": text},
        )
        if external_id in _MOCK_DB:
            existing = _MOCK_DB[external_id].get("comments", "")
            _MOCK_DB[external_id]["comments"] = f"{existing}\n{text}".strip()
        log.info("[MOCK ServiceNow] create_comment OK", sys_id=external_id)

    def update_status(self, external_id: str, status: str) -> None:
        sn_state = _NORMALISED_TO_SN_STATE.get(status, "1")
        self._log_would_call(
            "PATCH",
            f"/api/now/table/incident/{external_id}",
            body={"state": sn_state},
        )
        if external_id not in _MOCK_DB:
            raise ITSMTicketNotFoundError(
                f"[MOCK] ServiceNow incident not found: {external_id}"
            )
        _MOCK_DB[external_id]["state"] = sn_state
        log.info("[MOCK ServiceNow] update_status OK", sys_id=external_id, status=status, sn_state=sn_state)

    def close_ticket(self, external_id: str) -> None:
        self._log_would_call(
            "PATCH",
            f"/api/now/table/incident/{external_id}",
            body={"state": "5", "close_code": "Solved (Permanently)"},
        )
        if external_id not in _MOCK_DB:
            raise ITSMTicketNotFoundError(
                f"[MOCK] ServiceNow incident not found: {external_id}"
            )
        _MOCK_DB[external_id]["state"] = "5"
        log.info("[MOCK ServiceNow] close_ticket OK", sys_id=external_id)

    def parse_webhook_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Parse a ServiceNow business-rule HTTP webhook payload.

        ServiceNow webhook body shape (business rule → REST message):
        {
            "sys_id":            "abc123def456abc1",
            "number":            "INC0010001",
            "short_description": "...",
            "description":       "...",
            "state":             "1",
            "priority":          "2",
            "caller_id":         "user@corp.com"
        }
        """
        sys_id = payload.get("sys_id") or payload.get("number")
        if not sys_id:
            raise ITSMValidationError(
                "ServiceNow webhook payload missing 'sys_id' and 'number' fields."
            )

        # If the payload sys_id exists in mock DB, enrich with full record
        if sys_id in _MOCK_DB:
            raw = _MOCK_DB[sys_id]
        else:
            # Accept the payload as-is (new incident arriving via webhook)
            raw = dict(payload)
            raw.setdefault("sys_id", sys_id)
            _MOCK_DB[sys_id] = raw

        result = _normalise_sn(raw)
        log.info("[MOCK ServiceNow] parse_webhook_payload OK", sys_id=sys_id, summary=result["summary"])
        return result

    def get_sample_incidents(self) -> list[dict[str, Any]]:
        """
        Returns all sample incidents in normalized form.
        Used by the polling endpoint and for testing.
        """
        return [_normalise_sn(raw) for raw in _MOCK_DB.values()]


# ─────────────────────────────────────────────────────────────────────────────
# ServiceNowClient — FUTURE (real credentials not yet available)
# Enable once SERVICENOW_URL credentials are available:
#   1. Set SERVICENOW_MODE=real in .env
#   2. Fill in SERVICENOW_CLIENT_ID, SERVICENOW_CLIENT_SECRET, SERVICENOW_USERNAME, SERVICENOW_PASSWORD
#   3. Uncomment the `return ServiceNowClient()` line in get_servicenow_client()
# ─────────────────────────────────────────────────────────────────────────────

class ServiceNowClient(ITSMClient):
    """
    Real ServiceNow REST Table API client.
    Enable once SERVICENOW_URL credentials are available.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url       = settings.servicenow_url
        self._client_id      = settings.servicenow_client_id
        self._client_secret  = settings.servicenow_client_secret
        self._username       = settings.servicenow_username
        self._password       = settings.servicenow_password
        self._token: str | None = None

    # enable once SERVICENOW_URL credentials are available
    # def _get_oauth_token(self) -> str:
    #     import requests
    #     resp = requests.post(
    #         f"{self._base_url}/oauth_token.do",
    #         data={
    #             "grant_type":    "password",
    #             "client_id":     self._client_id,
    #             "client_secret": self._client_secret,
    #             "username":      self._username,
    #             "password":      self._password,
    #         },
    #     )
    #     resp.raise_for_status()
    #     return resp.json()["access_token"]
    #
    # def _headers(self) -> dict:
    #     if not self._token:
    #         self._token = self._get_oauth_token()
    #     return {"Authorization": f"Bearer {self._token}", "Accept": "application/json"}
    #
    # def fetch_ticket(self, external_id: str) -> dict:
    #     import requests
    #     resp = requests.get(
    #         f"{self._base_url}/api/now/table/incident/{external_id}",
    #         headers=self._headers(),
    #         params={"sysparm_display_value": "true"},
    #     )
    #     if resp.status_code == 404:
    #         raise ITSMTicketNotFoundError(f"ServiceNow incident not found: {external_id}")
    #     resp.raise_for_status()
    #     return _normalise_sn(resp.json()["result"])
    #
    # def create_comment(self, external_id: str, text: str) -> None:
    #     import requests
    #     requests.patch(
    #         f"{self._base_url}/api/now/table/incident/{external_id}",
    #         headers=self._headers(),
    #         json={"comments": text},
    #     ).raise_for_status()
    #
    # def update_status(self, external_id: str, status: str) -> None:
    #     import requests
    #     sn_state = _NORMALISED_TO_SN_STATE.get(status, "1")
    #     requests.patch(
    #         f"{self._base_url}/api/now/table/incident/{external_id}",
    #         headers=self._headers(),
    #         json={"state": sn_state},
    #     ).raise_for_status()
    #
    # def close_ticket(self, external_id: str) -> None:
    #     import requests
    #     requests.patch(
    #         f"{self._base_url}/api/now/table/incident/{external_id}",
    #         headers=self._headers(),
    #         json={"state": "5", "close_code": "Solved (Permanently)"},
    #     ).raise_for_status()
    #
    # def parse_webhook_payload(self, payload: dict) -> dict:
    #     sys_id = payload.get("sys_id") or payload.get("number")
    #     if not sys_id:
    #         raise ITSMValidationError("ServiceNow webhook missing sys_id/number")
    #     return _normalise_sn(payload)

    def fetch_ticket(self, external_id: str) -> dict[str, Any]:
        raise NotImplementedError("Enable ServiceNowClient once credentials are available")

    def create_comment(self, external_id: str, text: str) -> None:
        raise NotImplementedError("Enable ServiceNowClient once credentials are available")

    def update_status(self, external_id: str, status: str) -> None:
        raise NotImplementedError("Enable ServiceNowClient once credentials are available")

    def close_ticket(self, external_id: str) -> None:
        raise NotImplementedError("Enable ServiceNowClient once credentials are available")

    def parse_webhook_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError("Enable ServiceNowClient once credentials are available")


# ── Factory ───────────────────────────────────────────────────────────────────

@lru_cache(maxsize=1)
def get_servicenow_client() -> ITSMClient:
    """
    Returns the correct ServiceNow client based on SERVICENOW_MODE env var.
    Switch to real client by:
      1. Setting SERVICENOW_MODE=real
      2. Uncommenting `return ServiceNowClient()` below
    """
    settings = get_settings()
    if settings.servicenow_mode == "real":
        log.warning("SERVICENOW_MODE=real — real client not yet wired, falling back to mock")
        # return ServiceNowClient()  # enable once SERVICENOW_URL credentials are available
    return MockServiceNowClient()
