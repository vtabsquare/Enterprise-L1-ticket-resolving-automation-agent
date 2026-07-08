"""
graph_service.py — Microsoft Graph API + LDAP wrapper for AD/M365 actions.

Capabilities:
  - Unlock Active Directory account (Graph or LDAP)
  - Reset user password (Graph API)
  - Add user to security group (Graph API)
  - Send email notification (Graph API)

Auth: MSAL client-credentials flow (app-only token, no user interaction).
LDAP fallback used when Graph API is unavailable or not configured.

Full implementation in Phase 5.
"""

import structlog
import requests
from functools import lru_cache
import uuid
from typing import Optional

import msal
from app.config import get_settings

log = structlog.get_logger(__name__)


def _check_response(resp: requests.Response, context: str) -> None:
    """Log Graph API error body before raising so every failure is observable."""
    if not resp.ok:
        log.warning(
            "Graph API error response",
            context=context,
            status_code=resp.status_code,
            body=resp.text,
        )
    resp.raise_for_status()


def _is_already_member_error(resp: requests.Response) -> bool:
    """Return True when Graph signals the user is already in the group (idempotent).

    Matches the specific OData message:
      'One or more added object references already exist for the
       following modified properties: \'members\'.'

    Requires BOTH 'already exist' AND 'members' so that unrelated 400
    errors (e.g. group-type restriction, missing field) are never
    silently swallowed as a harmless no-op.
    """
    if resp.status_code != 400:
        return False
    try:
        msg = resp.json().get("error", {}).get("message", "").lower()
        return "already exist" in msg and "members" in msg
    except Exception:
        return False


class GraphService:
    """
    Wrapper for Microsoft Graph API v1.0 and LDAP.
    Used by ToolExecutionAgent for AD/M365 actions.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._tenant_id     = settings.ms_tenant_id
        self._client_id     = settings.ms_client_id
        self._client_secret = settings.ms_client_secret
        self._authority     = settings.ms_authority
        self._object_id     = settings.ms_object_id
        
        # We only use real mode if we have valid tenant credentials
        self._is_mock       = not self._tenant_id or self._tenant_id == "mock_tenant_id"
        self._msal_app      = None
        
        if self._is_mock:
            log.info("GraphService initialised in MOCK mode (missing credentials)")
        else:
            log.info("GraphService initialised in REAL mode", tenant_id=self._tenant_id)
            self._msal_app = msal.ConfidentialClientApplication(
                self._client_id,
                authority=self._authority,
                client_credential=self._client_secret
            )

    def _get_access_token(self) -> str:
        """Acquire MSAL client-credentials token."""
        if self._is_mock or not self._msal_app:
            return "mock_token"
            
        result = self._msal_app.acquire_token_silent(
            scopes=["https://graph.microsoft.com/.default"], 
            account=None
        )
        if not result:
            result = self._msal_app.acquire_token_for_client(
                scopes=["https://graph.microsoft.com/.default"]
            )
            
        if "access_token" in result:
            return result["access_token"]
        else:
            log.error("Failed to acquire token from MSAL", error=result.get("error"), desc=result.get("error_description"))
            raise RuntimeError(f"MSAL Auth failed: {result.get('error_description')}")
            
    def _get_headers(self) -> dict:
        token = self._get_access_token()
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

    def unlock_account(self, user_principal_name: str) -> dict:
        """
        Unlock a user's AD account via Graph API — state-aware.

        Flow:
          1. GET current accountEnabled value.
          2. If already True  -> log as explicit no-op; return {"changed": False, ...}
          3. If False         -> PATCH accountEnabled=True, re-read to confirm,
                               return {"changed": True, ...}

        Returns a dict (not a bare bool) so callers can distinguish a real
        re-enablement from an idempotent no-op.
        """
        if self._is_mock:
            log.info("GraphService.unlock_account (MOCK)", upn=user_principal_name)
            return {"changed": True, "was_enabled": False, "now_enabled": True, "note": "mock"}

        log.info("GraphService.unlock_account: reading current state", upn=user_principal_name)
        url = f"https://graph.microsoft.com/v1.0/users/{user_principal_name}"
        headers = self._get_headers()

        # Step 1: read current accountEnabled
        get_resp = requests.get(url, headers=headers, params={"$select": "accountEnabled"})
        _check_response(get_resp, "unlock_account/get_current_state")
        current_enabled = get_resp.json().get("accountEnabled")

        # Step 2: no-op path — account is already enabled, do not write
        if current_enabled is True:
            log.warning(
                "GraphService.unlock_account: no-op — account was not disabled",
                upn=user_principal_name,
                accountEnabled=current_enabled,
            )
            return {
                "changed": False,
                "was_enabled": True,
                "now_enabled": True,
                "note": "account was already enabled; no write performed",
            }

        # Step 3: account is disabled — PATCH to re-enable
        log.info("GraphService.unlock_account: account is disabled, patching", upn=user_principal_name)
        patch_resp = requests.patch(url, headers=headers, json={"accountEnabled": True})
        _check_response(patch_resp, "unlock_account/patch")

        # Step 4: re-read to confirm write stuck (allow up to 10s for Graph replication)
        import time
        now_enabled = False
        for i in range(1, 6):
            time.sleep(2)
            confirm_resp = requests.get(url, headers=headers, params={"$select": "accountEnabled"})
            _check_response(confirm_resp, "unlock_account/confirm_state")
            now_enabled = confirm_resp.json().get("accountEnabled")
            log.info("Polling for accountEnabled", attempt=i, current_state=now_enabled)
            if now_enabled:
                break

        if not now_enabled:
            raise RuntimeError(
                f"unlock_account: PATCH returned 204 but accountEnabled is still False "
                f"on re-read after 10s for {user_principal_name}. Possible policy block."
            )

        log.info(
            "GraphService.unlock_account: account successfully re-enabled",
            upn=user_principal_name,
            was_enabled=False,
            now_enabled=True,
        )
        return {
            "changed": True,
            "was_enabled": False,
            "now_enabled": True,
            "note": "account was disabled; re-enabled via Graph PATCH and confirmed on re-read",
        }

    def reset_password(self, user_principal_name: str, temporary_password: str) -> bool:
        """
        Force-reset a user password via Graph API.
        PATCH /users/{upn} { passwordProfile: { forceChangePasswordNextSignIn: true, ... } }
        """
        if self._is_mock:
            log.info("GraphService.reset_password (MOCK)", upn=user_principal_name)
            return True
            
        log.info("GraphService.reset_password (REAL)", upn=user_principal_name)
        url = f"https://graph.microsoft.com/v1.0/users/{user_principal_name}"
        payload = {
            "passwordProfile": {
                "forceChangePasswordNextSignIn": True,
                "password": temporary_password
            }
        }
        
        response = requests.patch(url, headers=self._get_headers(), json=payload)
        _check_response(response, "reset_password")
        return True

    def add_to_group(self, user_principal_name: str, group_id: str) -> bool:
        """
        Add user to an M365/AD security group.
        POST /groups/{group_id}/members/$ref
        """
        if self._is_mock:
            log.info("GraphService.add_to_group (MOCK)", upn=user_principal_name, group_id=group_id)
            return True
            
        log.info("GraphService.add_to_group (REAL)", upn=user_principal_name, group_id=group_id)
        url = f"https://graph.microsoft.com/v1.0/groups/{group_id}/members/$ref"
        payload = {
            "@odata.id": f"https://graph.microsoft.com/v1.0/users/{user_principal_name}"
        }
        
        response = requests.post(url, headers=self._get_headers(), json=payload)
        if _is_already_member_error(response):
            log.info("GraphService.add_to_group: user already a member (idempotent)", upn=user_principal_name, group_id=group_id)
            return True
        _check_response(response, "add_to_group")
        return True

    def add_to_distribution_list(self, user_principal_name: str, list_email: str) -> bool:
        """
        Add user to a distribution list by its email address.
        First resolves the group ID via GET /groups?$filter=mail eq '...',
        then adds the user to the group.
        """
        if self._is_mock:
            log.info("GraphService.add_to_distribution_list (MOCK)", upn=user_principal_name, list_email=list_email)
            return True

        log.info("GraphService.add_to_distribution_list (REAL)", upn=user_principal_name, list_email=list_email)
        headers = self._get_headers()
        
        # 1. Resolve list email to group ID
        search_url = f"https://graph.microsoft.com/v1.0/groups?$filter=mail eq '{list_email}'"
        search_resp = requests.get(search_url, headers=headers)
        _check_response(search_resp, "add_to_distribution_list/group_search")
        
        data = search_resp.json()
        if not data.get("value"):
            raise ValueError(f"Distribution list not found: {list_email}")
            
        group_id = data["value"][0]["id"]
        
        # 2. Add user to the resolved group
        add_url = f"https://graph.microsoft.com/v1.0/groups/{group_id}/members/$ref"
        payload = {
            "@odata.id": f"https://graph.microsoft.com/v1.0/users/{user_principal_name}"
        }
        
        add_resp = requests.post(add_url, headers=headers, json=payload)
        if _is_already_member_error(add_resp):
            log.info("GraphService.add_to_distribution_list: user already a member (idempotent)", upn=user_principal_name, list_email=list_email)
            return True
        _check_response(add_resp, "add_to_distribution_list/members_ref")
        log.info(
            "GraphService.add_to_distribution_list: member added",
            upn=user_principal_name,
            list_email=list_email,
            group_id=group_id,
            status_code=add_resp.status_code,
        )
        return True

    def send_email(self, to: str, subject: str, body: str) -> bool:
        """
        Send an email via Graph API.
        POST /users/{sender}/sendMail
        """
        if self._is_mock:
            log.info("GraphService.send_email (MOCK)", to=to, subject=subject)
            return True
            
        # We need a sender object ID or UPN to send mail as.
        # Fallback to the target user if object ID isn't provided (just for testing purposes).
        sender = self._object_id if self._object_id else to
            
        log.info("GraphService.send_email (REAL)", to=to, subject=subject, sender=sender)
        url = f"https://graph.microsoft.com/v1.0/users/{sender}/sendMail"
        payload = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "Text",
                    "content": body
                },
                "toRecipients": [
                    {
                        "emailAddress": {
                            "address": to
                        }
                    }
                ]
            },
            "saveToSentItems": "false"
        }
        
        response = requests.post(url, headers=self._get_headers(), json=payload)
        _check_response(response, "send_email")
        log.info(
            "GraphService.send_email: sent",
            to=to,
            subject=subject,
            sender=sender,
            status_code=response.status_code,
        )
        return True

    def _resolve_group_id(self, group_name_or_id: str) -> str:
        try:
            # If it's a valid UUID, return it
            import uuid
            uuid.UUID(group_name_or_id)
            return group_name_or_id
        except ValueError:
            pass
            
        if self._is_mock:
            return "mock-group-id"
            
        # Not a UUID, look it up by displayName
        url = f"https://graph.microsoft.com/v1.0/groups?$filter=displayName eq '{group_name_or_id}'"
        response = requests.get(url, headers=self._get_headers())
        _check_response(response, "_resolve_group_id")
        
        data = response.json().get("value", [])
        if len(data) == 1:
            return data[0]["id"]
        elif len(data) == 0:
            raise ValueError(f"Group '{group_name_or_id}' not found in AD.")
        else:
            raise ValueError(f"Multiple groups found matching '{group_name_or_id}'. Escalating for manual disambiguation.")

    def check_group_membership(self, user_principal_name: str, group_name_or_id: str) -> bool:
        """
        Check if user is a member of the specified group using checkMemberGroups.
        Resolves group names to IDs automatically.
        """
        group_id = self._resolve_group_id(group_name_or_id)
        if self._is_mock:
            log.info("GraphService.check_group_membership (MOCK)", upn=user_principal_name, group_id=group_id)
            return True
            
        log.info("GraphService.check_group_membership (REAL)", upn=user_principal_name, group_id=group_id)
        url = f"https://graph.microsoft.com/v1.0/users/{user_principal_name}/checkMemberGroups"
        payload = {"groupIds": [group_id]}
        
        response = requests.post(url, headers=self._get_headers(), json=payload)
        _check_response(response, "check_group_membership")
        
        member_groups = response.json().get("value", [])
        return group_id in member_groups

    def health_check(self) -> bool:
        """Ping Graph API."""
        if self._is_mock:
            return True
            
        try:
            self._get_access_token()
            return True
        except Exception:
            return False


@lru_cache(maxsize=1)
def get_graph_service() -> GraphService:
    """Returns a cached GraphService singleton."""
    return GraphService()
