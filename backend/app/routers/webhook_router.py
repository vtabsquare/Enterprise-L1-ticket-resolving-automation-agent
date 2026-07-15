"""
webhook_router.py — Ingestion endpoints for ITSM webhooks.

Endpoints:
    POST /api/webhooks/jira
    POST /api/webhooks/servicenow

These endpoints receive payloads from external systems, normalize them
via the respective ITSM clients, and upsert the ticket into Supabase.
"""

import hmac
import hashlib
import structlog
from fastapi import APIRouter, Request, HTTPException, status, BackgroundTasks
from typing import Any

from app.config import get_settings
from app.limiter import limiter
from app.services.jira_service import get_jira_client
from app.services.servicenow_service import get_servicenow_client
from app.services.itsm_client import ITSMValidationError
from app.agents.intake_agent import IntakeAgent
from app.orchestrator import Orchestrator

log = structlog.get_logger(__name__)

router = APIRouter(tags=["Webhooks"])


async def _process_webhook(source: str, normalized_ticket: dict[str, Any], background_tasks: BackgroundTasks) -> dict[str, Any]:
    """
    Common handler for normalized webhook payloads.
    Delegates to the IntakeAgent for deduplication, insertion, and logging.
    Then triggers the Orchestrator pipeline in the background.
    """
    try:
        ticket = IntakeAgent.process(source, normalized_ticket)
        # Run the full pipeline in the background so we return 200 OK immediately
        background_tasks.add_task(Orchestrator.process_ticket, ticket["id"])
        return {"status": "success", "ticket_id": ticket["id"], "message": "Pipeline triggered in background"}
    except Exception as e:
        log.error("IntakeAgent failed to process webhook", error=str(e), source=source)
        raise HTTPException(status_code=500, detail="Failed to ingest ticket")


async def verify_jira_signature(request: Request) -> None:
    settings = get_settings()
    secret = settings.jira_webhook_secret
    if not secret:
        return  # Check bypassed if no secret is configured
        
    signature = request.headers.get("x-hub-signature")
    if not signature:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing x-hub-signature header")
        
    body = await request.body()
    expected_hmac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    expected_signature = f"sha256={expected_hmac}"
    
    if not hmac.compare_digest(signature, expected_signature):
        log.warning("Invalid Jira webhook signature")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid webhook signature")

def sanitize_input(text: str | None, max_length: int = 5000) -> str | None:
    """Truncate extremely long text to prevent LLM DoS / prompt injection."""
    if not text:
        return text
    if len(text) > max_length:
        return text[:max_length] + "... [TRUNCATED]"
    return text

@router.post("/jira")
@limiter.limit("60/minute")
async def jira_webhook(request: Request, background_tasks: BackgroundTasks) -> dict[str, Any]:
    """
    Receive and process a Jira webhook with signature validation and rate limiting.
    """
    await verify_jira_signature(request)
    
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    log.info("Received Jira webhook")
    
    client = get_jira_client()
    try:
        normalized = client.parse_webhook_payload(payload)
        # Input Sanitization
        normalized["summary"] = sanitize_input(normalized.get("summary", ""))
        normalized["description"] = sanitize_input(normalized.get("description", ""))
    except ITSMValidationError as e:
        log.warning("Jira webhook validation failed", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.error("Error parsing Jira webhook", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error parsing payload")

    result = await _process_webhook("jira", normalized, background_tasks)
    return result


@router.post("/servicenow")
async def servicenow_webhook(request: Request, background_tasks: BackgroundTasks) -> dict[str, Any]:
    """
    Receive and process a ServiceNow webhook.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    log.info("Received ServiceNow webhook")
    
    client = get_servicenow_client()
    try:
        normalized = client.parse_webhook_payload(payload)
    except ITSMValidationError as e:
        log.warning("ServiceNow webhook validation failed", error=str(e))
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        log.error("Error parsing ServiceNow webhook", error=str(e))
        raise HTTPException(status_code=500, detail="Internal server error parsing payload")

    result = await _process_webhook("servicenow", normalized, background_tasks)
    return result
