"""
config.py — Centralised settings loader for the L1 Automation Platform.

Reads all environment variables from .env (via python-dotenv) and raises
a clear, descriptive error at startup if any required variable is missing.

No other module should read os.environ or load dotenv directly.
"""

import os
import sys
from functools import lru_cache
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

# Load .env file from the backend root (one level above app/)
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_ENV_FILE)


# ── Required variable names (startup will fail loudly if any are missing) ─────

_REQUIRED_VARS: list[tuple[str, str]] = [
    # (env_var_name, human-readable description)
    ("SUPABASE_URL",               "Supabase project URL"),
    ("SUPABASE_SERVICE_ROLE_KEY",  "Supabase service-role JWT"),
    ("SUPABASE_ANON_KEY",          "Supabase anon/public JWT"),
    ("GEMINI_API_KEY",             "Google Gemini API key"),
    ("JIRA_BASE_URL",              "Jira instance base URL"),
    ("JIRA_EMAIL",                 "Jira service-account email"),
    ("JIRA_API_TOKEN",             "Jira API token"),
    ("MS_TENANT_ID",               "Microsoft Azure tenant ID"),
    ("MS_CLIENT_ID",               "Microsoft Azure app client ID"),
    ("MS_CLIENT_SECRET",           "Microsoft Azure app client secret"),
]

def _validate_required_vars() -> None:
    """
    Called once at startup. Prints ALL missing variables at once
    (not one-at-a-time) so the operator can fix everything in one pass.
    """
    required = list(_REQUIRED_VARS)
    if os.environ.get("SERVICENOW_MODE", "mock").lower() != "mock":
        required.extend([
            ("SERVICENOW_URL",             "ServiceNow instance URL"),
            ("SERVICENOW_CLIENT_ID",       "ServiceNow OAuth client ID"),
            ("SERVICENOW_CLIENT_SECRET",   "ServiceNow OAuth client secret"),
            ("SERVICENOW_USERNAME",        "ServiceNow username"),
            ("SERVICENOW_PASSWORD",        "ServiceNow password"),
        ])

    missing = [
        f"  • {name}  ({desc})"
        for name, desc in required
        if not os.environ.get(name, "").strip()
    ]
    if missing:
        lines = "\n".join(missing)
        print(
            f"\n[CONFIG ERROR] The following required environment variables are not set:\n"
            f"{lines}\n\n"
            f"Copy backend/.env.example to backend/.env and fill in real values.\n",
            file=sys.stderr,
        )
        sys.exit(1)


class Settings:
    """
    Single source of truth for every runtime configuration value.
    Reads from os.environ (populated by load_dotenv above).

    Access via get_settings() — never instantiate directly.
    """

    def __init__(self) -> None:
        _validate_required_vars()

        # ── Application ───────────────────────────────────────────────────────
        self.app_env: str               = os.environ.get("APP_ENV", "development")
        self.app_secret_key: str        = os.environ.get("APP_SECRET_KEY", "")
        self.log_level: str             = os.environ.get("LOG_LEVEL", "INFO").upper()

        # ── Supabase ──────────────────────────────────────────────────────────
        self.supabase_url: str               = os.environ["SUPABASE_URL"]
        self.supabase_service_role_key: str  = os.environ["SUPABASE_SERVICE_ROLE_KEY"]
        self.supabase_anon_key: str          = os.environ["SUPABASE_ANON_KEY"]
        self.database_url: str               = os.environ.get("DATABASE_URL", "")

        # ── Google Gemini ─────────────────────────────────────────────────────
        self.gemini_api_key: str             = os.environ["GEMINI_API_KEY"]
        self.gemini_model: str               = os.environ.get("GEMINI_MODEL", "gemini-1.5-flash")
        self.gemini_embedding_model: str     = os.environ.get("GEMINI_EMBEDDING_MODEL", "models/text-embedding-004")
        self.gemini_embedding_dimension: int = int(os.environ.get("GEMINI_EMBEDDING_DIMENSION", "768"))

        # ── Redis / Celery ────────────────────────────────────────────────────
        self.redis_url: str              = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        self.celery_broker_url: str      = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
        self.celery_result_backend: str  = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/1")

        # ── Jira ──────────────────────────────────────────────────────────────
        self.jira_base_url: str          = os.environ["JIRA_BASE_URL"]
        self.jira_email: str             = os.environ["JIRA_EMAIL"]
        self.jira_api_token: str         = os.environ["JIRA_API_TOKEN"]
        self.jira_project_key: str       = os.environ.get("JIRA_PROJECT_KEY", "KAN")
        self.jira_webhook_secret: str    = os.environ.get("JIRA_WEBHOOK_SECRET", "")

        # ── ServiceNow ────────────────────────────────────────────────────────
        self.servicenow_mode: str            = os.environ.get("SERVICENOW_MODE", "mock")
        self.servicenow_url: str             = os.environ.get("SERVICENOW_URL", "")
        self.servicenow_client_id: str       = os.environ.get("SERVICENOW_CLIENT_ID", "")
        self.servicenow_client_secret: str   = os.environ.get("SERVICENOW_CLIENT_SECRET", "")
        self.servicenow_username: str        = os.environ.get("SERVICENOW_USERNAME", "")
        self.servicenow_password: str        = os.environ.get("SERVICENOW_PASSWORD", "")
        self.servicenow_webhook_secret: str  = os.environ.get("SERVICENOW_WEBHOOK_SECRET", "")

        # ── Microsoft Graph API ───────────────────────────────────────────────
        self.ms_tenant_id: str       = os.environ["MS_TENANT_ID"]
        self.ms_client_id: str       = os.environ["MS_CLIENT_ID"]
        self.ms_client_secret: str   = os.environ["MS_CLIENT_SECRET"]
        self.ms_authority: str       = (
            os.environ.get("MS_AUTHORITY")
            or f"https://login.microsoftonline.com/{self.ms_tenant_id}"
        )
        self.ms_object_id: str       = os.environ.get("MS_OBJECT_ID", "")

        # ── Notification ──────────────────────────────────────────────────────
        # Used as the fallback recipient when no reporter_email is found on a ticket.
        # In dev/test, set this to your own address. In production, use a monitored queue.
        self.test_notification_email: str = os.environ.get("TEST_NOTIFICATION_EMAIL", "")

        # ── LDAP / Active Directory (optional) ────────────────────────────────
        self.ldap_server: str        = os.environ.get("LDAP_SERVER", "")
        self.ldap_bind_dn: str       = os.environ.get("LDAP_BIND_DN", "")
        self.ldap_bind_password: str = os.environ.get("LDAP_BIND_PASSWORD", "")
        self.ldap_base_dn: str       = os.environ.get("LDAP_BASE_DN", "")

        # ── Policy engine ─────────────────────────────────────────────────────
        self.policy_max_auto_risk: str       = os.environ.get("POLICY_MAX_AUTO_RISK", "low")
        self.policy_blocked_categories: str  = os.environ.get(
            "POLICY_BLOCKED_CATEGORIES", "finance,executive,security-critical"
        )

    # ── Convenience properties ────────────────────────────────────────────────

    @property
    def blocked_categories_list(self) -> list[str]:
        return [c.strip().lower() for c in self.policy_blocked_categories.split(",") if c.strip()]

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """
    Returns a cached singleton Settings instance.
    Validation runs exactly once at first call (startup).
    Use this everywhere — never instantiate Settings() directly.
    """
    return Settings()
