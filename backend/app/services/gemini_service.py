"""
gemini_service.py — Wrapper for Google Gemini 1.5 Flash.

Provides methods for:
- Classification (structured output: category + confidence)
- Embedding generation (768-dim text-embedding-004)
- Resolution Planning (structured output: action plan)

All LLM prompts are defined as constants at the top of this file.
"""

import json
import math
import re
import structlog
from functools import lru_cache
from typing import Any

import google.generativeai as genai

from app.config import get_settings

log = structlog.get_logger(__name__)

# ── PROMPTS ───────────────────────────────────────────────────────────────────

PROMPT_CLASSIFY_TICKET = """
You are an expert IT Level 1 Service Desk classifier.
Analyze the following IT support ticket and classify it into exactly ONE of the categories below.
Choose the most SPECIFIC matching category — do not fall back to a generic bucket if a precise one applies.

CATEGORIES AND EXAMPLES:

# Account / Password
- password_reset          → "I forgot my Windows password", "My domain password expired and I'm locked out", "Reset my AD credentials"
- account_unlock          → "My account is locked after too many failed attempts", "AD account locked, please unlock", "Locked out of domain login"
- password_expiry_assistance → "My password is about to expire, how do I change it?", "Got a warning that password expires in 5 days", "How do I update my password before it expires?"

# VPN
- vpn_connectivity_issue  → "VPN keeps disconnecting", "VPN connects but I can't reach internal resources", "VPN is slow and dropping"
- vpn_password_reset      → "My VPN password expired", "Can't log into VPN due to wrong password", "Need to reset my VPN credentials"
- vpn_account_unlock      → "VPN account is locked after failed attempts", "Locked out of Cisco AnyConnect", "VPN authentication failing, account locked"
- vpn_access_request      → "New contractor needs VPN access", "Please provision VPN for my team member", "Request VPN access for new hire"
- vpn_profile_reset       → "VPN profile is corrupted", "Need to reinstall VPN client profile", "VPN config stuck, how do I reset it?"

# Active Directory / Identity
- user_enable_disable     → "Please disable the account of departing employee", "Enable account for returning employee", "Deactivate AD account for John Smith"
- group_membership_validation → "Check if user is in the correct security group", "Validate group membership for audit", "Is user in the VPN Users group?"

# Software Access / Licensing
- software_access         → "Need access to Salesforce", "Request Adobe license", "Can't log into the CRM system"
- software_install_request → "Please install Visual Studio on my laptop", "Need AutoCAD installed", "Can you push the Zoom client to my machine?"

# Email / Mailbox
- email_issue             → "Can't send or receive emails", "Outlook keeps crashing", "Email stuck in outbox"
- mailbox_access_issue    → "Can't access shared mailbox", "Missing permissions on HR mailbox", "Shared inbox not showing in Outlook"
- outlook_profile_reset   → "Outlook profile is corrupted, need to recreate it", "Outlook keeps asking for password after profile issue", "Need to reset my Outlook profile"
- distribution_list_update → "Add new member to the finance DL", "Remove ex-employee from mailing list", "Update distribution group membership"
- mail_forwarding_request → "Set up mail forwarding for departing employee", "Forward emails from old account to new", "Auto-forward my emails while on leave"
- shared_folder_access    → "Need access to the shared drive folder", "Can't open shared network folder", "Request permissions on SharePoint folder"

# Hardware
- hardware_issue          → "My laptop won't turn on", "Screen is cracked", "Keyboard not working"
- printer_issue           → "Printer not found on network", "Can't print from my laptop", "Printer showing offline"

# Network
- network_connectivity    → "No internet connection", "Network is down in Building 3", "Can't connect to WiFi"
- network_adapter_issue   → "Network adapter shows as disabled", "Ethernet adapter not detected", "WiFi adapter missing from Device Manager"
- dns_flush_guidance      → "Getting DNS errors", "Site not resolving, how do I flush DNS?", "DNS cache issue, need guidance"

# Onboarding / Offboarding
- onboarding              → "New employee starting Monday, please set up accounts", "Set up laptop and email for new hire", "Provision new joiner"
- offboarding             → "Employee leaving, please revoke access", "Disable all accounts for departing staff", "Exit process for terminated employee"

# General / Fallback
- general_it              → Anything IT-related that doesn't fit a specific category above
- unknown                 → Cannot determine category from available information

You must output ONLY valid JSON in the following format, with no markdown formatting or extra text:
{{
    "category": "the_chosen_category",
    "confidence": 0.95
}}

Ticket Summary:
{summary}

Ticket Description:
{description}
"""


PROMPT_GENERATE_PLAN = """
You are an expert IT Level 1 Service Desk agent.
Your job is to read an IT support ticket, its classification, and relevant knowledge base (KB) articles,
and output a structured resolution plan.

IMPORTANT RULE: You do NOT execute actions. You only output a plan.

─────────────────────────────────────────────────────────────────────────────
GENERAL TIE-BREAKING RULE:
When multiple action_types are plausible for a category, prefer the
LOWER-RISK, NON-DESTRUCTIVE action (e.g. send_email with KB guidance)
UNLESS the ticket text explicitly requests immediate execution of a
higher-risk action (e.g. "reset my password now", "unlock immediately").
─────────────────────────────────────────────────────────────────────────────

─────────────────────────────────────────────────────────────────────────────
CATEGORY-TO-ACTION MAPPING (use these as your defaults — do not deviate):

# Account / Password
- password_reset               → proposed_action: password_reset
                                  (only when user says "reset now" / "reset immediately")
- password_expiry_assistance   → proposed_action: send_email
                                  (KB guidance: explain how to change password before expiry)
                                  EXCEPTION: if ticket says "reset it for me now" → password_reset
- account_unlock               → proposed_action: ad_unlock
                                  (always — no ambiguity, safe auto-action)

# VPN
- vpn_connectivity_issue       → proposed_action: send_email
                                  (KB troubleshooting steps for connectivity drops)
- vpn_password_reset           → proposed_action: send_email
                                  (KB guidance: VPN uses AD credentials, user can self-serve via SSPR)
                                  EXCEPTION: ticket explicitly confirms VPN uses separate credentials
                                  AND requests a reset → password_reset
- vpn_account_unlock           → proposed_action: ad_unlock
                                  (locked VPN/AD account — safe to auto-unlock)
- vpn_access_request           → proposed_action: group_add
                                  (provision user into VPN security group)
- vpn_profile_reset            → proposed_action: send_email
                                  (KB steps to delete and reinstall VPN client profile)

# Active Directory / Identity
- user_enable_disable          → proposed_action: escalate
                                  (high-risk write action — always requires human approval)
- group_membership_validation  → proposed_action: send_email
                                  (read-only check — post result as KB guidance reply)

# Software Access / Licensing
- software_access              → proposed_action: group_add
                                  (provision group membership for the application)
- software_install_request     → proposed_action: escalate
                                  (no endpoint agent — always route to Desktop Support)

# Email / Mailbox
- email_issue                  → proposed_action: send_email
                                  (KB troubleshooting steps for send/receive issues)
- mailbox_access_issue         → proposed_action: send_email
                                  (KB steps to request shared mailbox permissions)
- outlook_profile_reset        → proposed_action: send_email
                                  (KB steps to delete and recreate Outlook profile)
- distribution_list_update     → proposed_action: dl_update
                                  (adds a user to a DL by email address or display name)
- mail_forwarding_request      → proposed_action: escalate
                                  (write action — not yet automated, route to Email Team)
- shared_folder_access         → proposed_action: escalate
                                  (requires manager approval workflow)

# Hardware
- hardware_issue               → proposed_action: escalate
                                  (physical issue — always requires human hands-on)
- printer_issue                → proposed_action: escalate
                                  (no endpoint agent — route to Desktop Support)

# Network
- network_connectivity         → proposed_action: send_email
                                  (KB troubleshooting: check cable, restart adapter, etc.)
- network_adapter_issue        → proposed_action: send_email
                                  (KB steps to re-enable adapter via Device Manager)
- dns_flush_guidance           → proposed_action: send_email
                                  (KB steps for ipconfig /flushdns and DNS troubleshooting)

# Onboarding / Offboarding
- onboarding                   → proposed_action: escalate
                                  (multi-step provisioning — human required)
- offboarding                  → proposed_action: escalate
                                  (access revocation — human required for safety)

# General / Fallback
- general_it                   → proposed_action: send_email
                                  (generic KB guidance or acknowledgement)
- unknown                      → proposed_action: escalate
                                  (cannot determine a safe action — route to human)
─────────────────────────────────────────────────────────────────────────────

Output ONLY valid JSON in the following format, with no markdown formatting or extra text:
{{
    "reasoning": "Explain step-by-step why you chose this plan, referencing the KB articles, ticket wording, and the category-to-action mapping above.",
    "proposed_action": "MUST be exactly one of: 'password_reset', 'ad_unlock', 'group_add', 'send_email', 'escalate', 'dl_update'",
    "target_system": "The specific system this action applies to. Use 'ad' for AD actions, 'graph' for send_email, 'jira' or 'servicenow' for ITSM actions.",
    "action_payload": {{
        "user_email": "the reporter's email address if identifiable from the ticket text, otherwise leave as empty string",
        "list_email": "for dl_update: the email or best guess name of the distribution list from the ticket text",
        "subject": "for send_email: a concise, helpful subject line for the guidance email",
        "body": "for send_email: the full guidance text to send to the user, drawn from the matched KB articles"
    }},
    "risk_level": "low | medium | high",
    "plan_confidence": 0.95
}}

Ticket Summary:
{summary}

Ticket Description:
{description}

Ticket Reporter Email:
{reporter_email}

Classification:
{classification}

Relevant Knowledge Base Articles:
{kb_context}
"""



class GeminiService:
    """Wrapper class for Google Gemini operations."""

    def __init__(self) -> None:
        settings = get_settings()
        genai.configure(api_key=settings.gemini_api_key)
        self.model_name = settings.gemini_model
        self.embedding_model_name = settings.gemini_embedding_model
        log.info(
            "GeminiService initialised",
            model=self.model_name,
            embedding_model=self.embedding_model_name,
        )

    def _parse_json_response(self, text: str) -> dict[str, Any]:
        """Cleans markdown backticks and parses JSON robustly."""
        # Use regex to find everything between ```json and ``` or just ``` and ```
        match = re.search(r'```(?:json)?\s*(.*?)\s*```', text, re.DOTALL)
        if match:
            clean_text = match.group(1)
        else:
            clean_text = text.strip()
            
        try:
            return json.loads(clean_text)
        except json.JSONDecodeError as e:
            # Re-raise so the caller can handle the fallback correctly
            raise e

    def classify_ticket(self, summary: str, description: str | None) -> dict[str, Any]:
        """
        Classifies a ticket into a predefined category.

        Returns:
            dict: {"category": str, "confidence": float}
        """
        prompt = PROMPT_CLASSIFY_TICKET.format(
            summary=summary,
            description=description or "No description provided."
        )
        
        log.info("Calling Gemini for ticket classification")
        model = genai.GenerativeModel(self.model_name)
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.1,  # Low temperature for deterministic classification
                response_mime_type="application/json"
            )
        )

        # DEBUG: Log the raw unprocessed text from Gemini before any parsing.
        # This lets us see exactly what format the model is returning.
        raw_text = getattr(response, "text", "<no .text attribute on response>")
        log.debug("Raw Gemini classification response", raw_gemini_text=raw_text)

        try:
            result = self._parse_json_response(raw_text)
            # Validate expected keys are present before returning
            if "category" not in result or "confidence" not in result:
                log.error(
                    "Gemini response parsed as JSON but missing expected keys",
                    raw_gemini_text=raw_text,
                    parsed_keys=list(result.keys()),
                )
                return {"category": "unknown", "confidence": 0.0}
            log.info("Ticket classified", category=result["category"], confidence=result["confidence"])
            return result
        except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
            log.error(
                "Failed to parse Gemini classification response",
                raw_gemini_text=raw_text,
                error=str(e),
                error_type=type(e).__name__,
            )
            return {"category": "unknown", "confidence": 0.0}

    def generate_embedding(self, text: str) -> list[float]:
        """
        Generates a 768-dimensional vector embedding for the input text.
        """
        log.info("Calling Gemini for embedding generation")
        # Ensure we don't pass empty strings to embedding model
        if not text.strip():
            text = "empty"
            
        result = genai.embed_content(
            model=self.embedding_model_name,
            content=text,
            task_type="retrieval_document",
            output_dimensionality=768
        )
        
        embedding = result['embedding']
        
        # gemini-embedding-001 does not auto-normalize when output_dimensionality < 3072
        # We must manually normalize (divide by L2 norm) to ensure cosine similarity works
        norm = math.sqrt(sum(x * x for x in embedding))
        if norm > 0:
            embedding = [x / norm for x in embedding]
            
        return embedding

    def generate_plan(
        self,
        ticket: dict[str, Any],
        classification: dict[str, Any],
        kb_context: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """
        Generates a resolution plan based on ticket, classification, and KB context.

        Returns:
            dict: {"reasoning": str, "proposed_action": str, "action_payload": dict, "risk_level": str}
        """
        # Format KB context for the prompt
        formatted_kb = ""
        for kb in kb_context:
            formatted_kb += f"\n--- {kb.get('title')} ---\n{kb.get('content')}\n"
            
        if not formatted_kb.strip():
            formatted_kb = "No relevant knowledge base articles found."

        prompt = PROMPT_GENERATE_PLAN.format(
            summary=ticket.get("summary", ""),
            description=ticket.get("description", "No description provided."),
            reporter_email=ticket.get("reporter_email", ""),
            classification=json.dumps(classification, indent=2),
            kb_context=formatted_kb
        )

        log.info("Calling Gemini for resolution planning")
        model = genai.GenerativeModel(self.model_name)
        response = model.generate_content(
            prompt,
            generation_config=genai.types.GenerationConfig(
                temperature=0.2,
                response_mime_type="application/json"
            )
        )

        try:
            result = self._parse_json_response(response.text)
            log.info("Resolution plan generated", action=result.get("proposed_action"), risk=result.get("risk_level"))
            return result
        except json.JSONDecodeError as e:
            log.error("Failed to parse Gemini plan response", text=response.text, error=str(e))
            # Fallback plan triggering escalation
            return {
                "reasoning": "Failed to parse LLM response into JSON.",
                "proposed_action": "escalate",
                "action_payload": {},
                "risk_level": "high"
            }


@lru_cache(maxsize=1)
def get_gemini_service() -> GeminiService:
    return GeminiService()
