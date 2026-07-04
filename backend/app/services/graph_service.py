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
from typing import Optional

import msal
from app.config import get_settings

log = structlog.get_logger(__name__)


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

    def unlock_account(self, user_principal_name: str) -> bool:
        """
        Unlock a user's AD account via Graph API.
        PATCH /users/{upn} { accountEnabled: true }
        """
        if self._is_mock:
            log.info("GraphService.unlock_account (MOCK)", upn=user_principal_name)
            return True
            
        log.info("GraphService.unlock_account (REAL)", upn=user_principal_name)
        url = f"https://graph.microsoft.com/v1.0/users/{user_principal_name}"
        payload = {"accountEnabled": True}
        
        response = requests.patch(url, headers=self._get_headers(), json=payload)
        response.raise_for_status()
        return True

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
        response.raise_for_status()
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
        response.raise_for_status()
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
        search_resp.raise_for_status()
        
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
        add_resp.raise_for_status()
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
        response.raise_for_status()
        return True

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
