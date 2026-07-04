"""
jira_service.py — Real Jira REST API v3 implementation of ITSMClient.

Class: JiraClient(ITSMClient)

Auth: HTTP Basic — JIRA_EMAIL + JIRA_API_TOKEN against JIRA_BASE_URL.
All calls use the requests library with the v3 REST API.

All Jira-specific field names, status transitions, and API paths are
confined to THIS FILE ONLY. Nothing outside this file references
any Jira-specific concept.
"""

import structlog
import requests
from functools import lru_cache
from requests.auth import HTTPBasicAuth
from typing import Any

from app.config import get_settings
from app.services.itsm_client import (
    ITSMClient,
    ITSMError,
    ITSMTicketNotFoundError,
    ITSMConnectionError,
    ITSMValidationError,
)

log = structlog.get_logger(__name__)

# ── Status mapping: normalised → Jira transition names ───────────────────────
_STATUS_TO_JIRA_TRANSITION = {
    "open":        ["to do", "open", "backlog"],
    "in_progress": ["in progress", "in development", "start progress"],
    "resolved":    ["done", "resolve", "resolved", "close"],
    "closed":      ["done", "close", "closed"],
}

# ── Priority mapping: Jira → normalised ───────────────────────────────────────
_JIRA_PRIORITY_MAP = {
    "highest": "critical",
    "high":    "high",
    "medium":  "medium",
    "low":     "low",
    "lowest":  "low",
}

# ── Status mapping: Jira status name → normalised ─────────────────────────────
_JIRA_STATUS_MAP = {
    "to do":       "open",
    "open":        "open",
    "in progress": "in_progress",
    "done":        "resolved",
    "resolved":    "resolved",
    "closed":      "closed",
}


def _normalise(issue_json: dict[str, Any], source: str = "jira") -> dict[str, Any]:
    """
    Maps a Jira issue REST response to the source-agnostic normalized dict.
    This is the ONLY place Jira field names are referenced.
    """
    fields = issue_json.get("fields", {})
    raw_status   = (fields.get("status")   or {}).get("name", "").lower()
    raw_priority = (fields.get("priority") or {}).get("name", "").lower()
    reporter     = fields.get("reporter") or {}
    assignee     = fields.get("assignee") or {}

    return {
        "external_id":    issue_json.get("key", ""),
        "source":         source,
        "summary":        fields.get("summary", ""),
        "description":    _extract_description(fields.get("description")),
        "status":         _JIRA_STATUS_MAP.get(raw_status, "open"),
        "priority":       _JIRA_PRIORITY_MAP.get(raw_priority, "medium"),
        "reporter_email": reporter.get("emailAddress"),
        "raw":            issue_json,
    }


def _extract_description(desc_field: Any) -> str | None:
    """
    Jira v3 description is Atlassian Document Format (ADF) JSON, not plain text.
    Extract readable text from ADF content nodes.
    """
    if desc_field is None:
        return None
    if isinstance(desc_field, str):
        return desc_field
    # ADF format: { "type": "doc", "content": [ ... ] }
    if isinstance(desc_field, dict):
        parts = []
        for block in desc_field.get("content", []):
            for inline in block.get("content", []):
                if inline.get("type") == "text":
                    parts.append(inline.get("text", ""))
        return " ".join(parts).strip() or None
    return None


class JiraClient(ITSMClient):
    """
    Real Jira REST API v3 client.

    Uses requests library directly against the v3 REST API.
    Authenticated with HTTP Basic (JIRA_EMAIL : JIRA_API_TOKEN).
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url    = settings.jira_base_url.rstrip("/")
        self._auth        = HTTPBasicAuth(settings.jira_email, settings.jira_api_token)
        self._project_key = settings.jira_project_key
        self._headers     = {
            "Accept":       "application/json",
            "Content-Type": "application/json",
        }
        log.info("JiraClient initialised", base_url=self._base_url, project=self._project_key)

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get(self, path: str) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        try:
            resp = requests.get(url, auth=self._auth, headers=self._headers, timeout=15)
            if resp.status_code == 404:
                raise ITSMTicketNotFoundError(f"Jira issue not found: {path}")
            resp.raise_for_status()
            return resp.json()
        except ITSMTicketNotFoundError:
            raise
        except requests.RequestException as exc:
            raise ITSMConnectionError(f"Jira GET {url} failed: {exc}") from exc

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{self._base_url}{path}"
        try:
            resp = requests.post(url, auth=self._auth, headers=self._headers,
                                 json=body, timeout=15)
            resp.raise_for_status()
            return resp.json() if resp.content else {}
        except requests.RequestException as exc:
            raise ITSMConnectionError(f"Jira POST {url} failed: {exc}") from exc

    def _put(self, path: str, body: dict[str, Any]) -> None:
        url = f"{self._base_url}{path}"
        try:
            resp = requests.put(url, auth=self._auth, headers=self._headers,
                                json=body, timeout=15)
            resp.raise_for_status()
        except requests.RequestException as exc:
            raise ITSMConnectionError(f"Jira PUT {url} failed: {exc}") from exc

    def _get_transitions(self, external_id: str) -> list[dict[str, Any]]:
        data = self._get(f"/rest/api/3/issue/{external_id}/transitions")
        return data.get("transitions", [])

    def _do_transition(self, external_id: str, target_names: list[str]) -> None:
        """Find a matching transition by name (case-insensitive) and execute it."""
        transitions = self._get_transitions(external_id)
        for t in transitions:
            if t.get("name", "").lower() in target_names:
                self._post(
                    f"/rest/api/3/issue/{external_id}/transitions",
                    {"transition": {"id": t["id"]}},
                )
                log.info("Jira transition applied", issue=external_id, transition=t["name"])
                return
        log.warning(
            "No matching Jira transition found",
            issue=external_id,
            wanted=target_names,
            available=[t.get("name") for t in transitions],
        )

    # ── ITSMClient interface ──────────────────────────────────────────────────

    def fetch_ticket(self, external_id: str) -> dict[str, Any]:
        """Fetch a single Jira issue and return a normalized dict."""
        raw = self._get(f"/rest/api/3/issue/{external_id}")
        result = _normalise(raw)
        log.info("JiraClient.fetch_ticket", key=external_id, status=result["status"])
        return result

    def create_comment(self, external_id: str, text: str) -> None:
        """Post a plain-text comment to a Jira issue using ADF format."""
        body = {
            "body": {
                "type": "doc",
                "version": 1,
                "content": [
                    {
                        "type": "paragraph",
                        "content": [{"type": "text", "text": text}],
                    }
                ],
            }
        }
        self._post(f"/rest/api/3/issue/{external_id}/comment", body)
        log.info("JiraClient.create_comment", key=external_id)

    def update_status(self, external_id: str, status: str) -> None:
        """
        Transition a Jira issue to the nearest matching status.
        Maps normalised status → list of Jira transition names to try.
        """
        target_names = _STATUS_TO_JIRA_TRANSITION.get(status, [status.lower()])
        self._do_transition(external_id, target_names)
        log.info("JiraClient.update_status", key=external_id, status=status)

    def close_ticket(self, external_id: str) -> None:
        """Transition a Jira issue to Done/Resolved."""
        self._do_transition(external_id, _STATUS_TO_JIRA_TRANSITION["closed"])
        log.info("JiraClient.close_ticket", key=external_id)

    def parse_webhook_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """
        Parse a raw Jira webhook payload and return a normalized ticket dict.

        Jira webhook events relevant to us:
            jira:issue_created  — new ticket
            jira:issue_updated  — ticket field changed

        Jira webhook shape:
        {
            "webhookEvent": "jira:issue_created",
            "issue": {
                "id": "10042",
                "key": "KAN-5",
                "fields": { "summary": "...", "description": {...}, ... }
            },
            "user": { "emailAddress": "reporter@example.com" }
        }
        """
        event = payload.get("webhookEvent", "")
        issue = payload.get("issue")

        if not issue:
            raise ITSMValidationError(
                f"Jira webhook payload missing 'issue' field. event={event}"
            )

        if event not in ("jira:issue_created", "jira:issue_updated", "jira:issue_deleted"):
            log.warning("JiraClient.parse_webhook_payload: unexpected event", webhook_event=event)

        normalized = _normalise(issue)
        
        # Atlassian webhooks often redact the reporter object. If it's missing, fetch it via REST.
        if not normalized.get("reporter_email"):
            log.info("Webhook reporter_email missing, fetching full ticket via REST API fallback", key=normalized["external_id"])
            try:
                full_ticket = self.fetch_ticket(normalized["external_id"])
                if full_ticket.get("reporter_email"):
                    normalized["reporter_email"] = full_ticket.get("reporter_email")
                    normalized["raw"] = full_ticket.get("raw", normalized["raw"])
                    log.info("Fallback succeeded: retrieved reporter_email via REST API", key=normalized["external_id"])
                else:
                    log.warning("Fallback ran, but reporter_email is genuinely missing in Jira", key=normalized["external_id"])
            except Exception as e:
                log.warning("Failed to fetch full ticket for reporter_email fallback. Continuing without email.", error=str(e), key=normalized["external_id"])
        else:
            log.debug("Skipped REST API fallback (reporter_email was present in webhook)", key=normalized["external_id"])

        log.info(
            "JiraClient.parse_webhook_payload",
            webhook_event=event,
            key=normalized["external_id"],
        )
        return normalized


@lru_cache(maxsize=1)
def get_jira_client() -> JiraClient:
    """Returns a cached JiraClient singleton."""
    return JiraClient()
