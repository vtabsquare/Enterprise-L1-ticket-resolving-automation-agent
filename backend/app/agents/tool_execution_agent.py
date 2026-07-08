"""
tool_execution_agent.py — Executes approved ActionPlans against downstream APIs.
"""

import structlog
import time
from typing import Any

from app.schemas.action_plan import ActionPlan
from app.schemas.execution import ExecutionResult
from app.services.graph_service import get_graph_service
from app.agents.audit_agent import AuditAgent
from app.agents.agent_utils import retry_once, safe_call
from app.services import supabase_service
from app.config import get_settings

log = structlog.get_logger(__name__)

def _sanitize_text(text: str) -> str:
    """Replace common LLM-generated non-ASCII chars with ASCII equivalents.
    Prevents 'charmap' codec errors on Windows when structlog writes to stdout."""
    replacements = {
        "\u2192": "->",   # →
        "\u2190": "<-",   # ←
        "\u2022": "-",    # •
        "\u2013": "-",    # –
        "\u2014": "--",   # —
        "\u2018": "'",    # '
        "\u2019": "'",    # '
        "\u201c": '"',    # "
        "\u201d": '"',    # "
        "\u2026": "...",  # …
    }
    for char, replacement in replacements.items():
        text = text.replace(char, replacement)
    return text


class ToolExecutionAgent:
    """
    Executes an approved ActionPlan.
    Contains strict try/except and retry boundaries so failed execution
    never crashes the orchestrator pipeline.
    """

    @staticmethod
    def execute(ticket_id: str, action_plan: ActionPlan) -> ExecutionResult:
        """
        Execute the tool specified in action_plan.
        Retries exactly once on failure.
        """
        log.info("ToolExecutionAgent starting", ticket_id=ticket_id, action_type=action_plan.action_type)

        if action_plan.action_type == "escalate":
            raise ValueError("ToolExecutionAgent should never receive 'escalate'. PolicyEngine must intercept this.")

        graph = get_graph_service()
        params = action_plan.parameters

        def _attempt() -> Any:
            """Inner function to route the action and execute it."""
            if action_plan.action_type == "password_reset":
                # Fallback to generating a temp password if one wasn't planned
                temp_pw = params.get("temporary_password", "TempPass123!")
                return graph.reset_password(
                    user_principal_name=params.get("user_email", ""),
                    temporary_password=temp_pw
                )
            elif action_plan.action_type == "ad_unlock":
                return graph.unlock_account(
                    user_principal_name=params.get("user_email", "")
                )
            elif action_plan.action_type == "group_add":
                return graph.add_to_group(
                    user_principal_name=params.get("user_email", ""),
                    group_id=params.get("group_id", params.get("group", "UnknownGroup"))
                )
            elif action_plan.action_type == "dl_update":
                return graph.add_to_distribution_list(
                    user_principal_name=params.get("user_email", ""),
                    list_email=params.get("list_email", "")
                )
            elif action_plan.action_type == "check_group_membership":
                user_email = params.get("user_email", "")
                group_name_or_id = params.get("group_id", params.get("group", "UnknownGroup"))
                is_member = graph.check_group_membership(
                    user_principal_name=user_email,
                    group_name_or_id=group_name_or_id,
                )

                membership_status = "is" if is_member else "is NOT"
                answer = f"{'Yes' if is_member else 'No'}, {user_email} {membership_status} a member of {group_name_or_id}."

                ticket_row = retry_once(
                    lambda: supabase_service.get_ticket_by_id(ticket_id),
                    agent="ToolExecutionAgent", ticket_id=ticket_id, call="Supabase get_ticket_by_id",
                )
                reporter_email = (ticket_row or {}).get("reporter_email") if ticket_row else None
                settings = get_settings()

                recipient = (
                    params.get("user_email")
                    or params.get("to")
                    or reporter_email
                    or settings.test_notification_email
                )

                if not recipient:
                    raise ValueError("check_group_membership: no recipient available to send confirmation email")

                email_subject = f"Group membership result: {group_name_or_id}"
                email_body = (
                    f"Group membership verification completed.\n\n"
                    f"User: {user_email}\n"
                    f"Group: {group_name_or_id}\n"
                    f"Result: {answer}"
                )

                email_sent = graph.send_email(
                    to=recipient,
                    subject=_sanitize_text(email_subject),
                    body=_sanitize_text(email_body),
                )
                return {
                    "is_member": is_member,
                    "user_email": user_email,
                    "group": group_name_or_id,
                    "answer": answer,
                    "email_sent": email_sent,
                }
            elif action_plan.action_type == "send_email":
                # Recipient priority:
                #   1. Gemini's plan explicitly set user_email / to in parameters
                #   2. reporter_email stored on the ticket (from Jira/ServiceNow webhook)
                #   3. TEST_NOTIFICATION_EMAIL from .env (dev/test fallback)
                ticket_row = retry_once(
                    lambda: supabase_service.get_ticket_by_id(ticket_id),
                    agent="ToolExecutionAgent", ticket_id=ticket_id, call="Supabase get_ticket_by_id",
                )
                reporter_email = (ticket_row or {}).get("reporter_email") if ticket_row else None
                settings = get_settings()
                fallback = settings.test_notification_email

                recipient = (
                    params.get("user_email")
                    or params.get("to")
                    or reporter_email
                    or fallback
                )

                if not recipient:
                    raise ValueError(
                        "send_email: no recipient available — set TEST_NOTIFICATION_EMAIL in .env"
                    )

                log.info(
                    "send_email recipient resolved",
                    ticket_id=ticket_id,
                    recipient=recipient,
                    source="plan" if (params.get("user_email") or params.get("to")) else
                            "reporter_email" if reporter_email else "TEST_NOTIFICATION_EMAIL"
                )

                return graph.send_email(
                    to=recipient,
                    subject=_sanitize_text(params.get("subject", "IT Helpdesk Update")),
                    body=_sanitize_text(params.get("body", "Please contact IT support."))
                )
            else:
                raise ValueError(f"Unknown action_type mapped to ToolExecutionAgent: {action_plan.action_type}")

        retries = 0
        success = False
        noop = False          # True when ad_unlock found account already enabled
        message = ""
        raw_response = None

        # Execution loop (1 initial attempt + 1 retry = 2 max attempts)
        for attempt in range(2):
            try:
                result_data = _attempt()

                # ad_unlock returns a dict — inspect it to distinguish real vs no-op
                if action_plan.action_type == "check_group_membership" and isinstance(result_data, dict):
                    message = result_data["answer"]
                    raw_response = result_data
                elif action_plan.action_type == "ad_unlock" and isinstance(result_data, dict):
                    if result_data.get("changed") is False:
                        noop = True
                        message = (
                            f"ad_unlock: no-op — account '{action_plan.parameters.get('user_email')}' "
                            f"was already enabled; no write performed"
                        )
                        raw_response = result_data
                    else:
                        message = (
                            f"ad_unlock: account successfully re-enabled — "
                            f"{result_data.get('note', '')}"
                        )
                        raw_response = result_data
                else:
                    message = f"Successfully executed '{action_plan.action_type}'"

                success = True
                break

            except Exception as e:
                log.warning(
                    "Tool execution failed",
                    ticket_id=ticket_id,
                    attempt=attempt+1,
                    error=str(e)
                )
                if attempt == 0:
                    retries = 1
                    time.sleep(1) # simple backoff
                else:
                    success = False
                    message = f"Failed to execute '{action_plan.action_type}': {str(e)}"
                    raw_response = {"error": str(e), "type": type(e).__name__}

        # Build final result
        result = ExecutionResult(
            success=success,
            message=message,
            raw_response=raw_response,
            retries_attempted=retries
        )

        # agent_action: noop gets its own status so the DB is unambiguous
        action_status = "noop" if noop else ("success" if success else "failed")
        safe_call(
            lambda: retry_once(
                lambda: supabase_service.insert_agent_action({
                    "ticket_id": ticket_id,
                    "agent_name": "ToolExecutionAgent",
                    "action_type": "tool_execute",
                    "payload": result.model_dump(),
                    "status": action_status,
                }),
                agent="ToolExecutionAgent", ticket_id=ticket_id, call="Supabase insert_agent_action",
            ),
            agent="ToolExecutionAgent", ticket_id=ticket_id,
            call="Supabase insert_agent_action",
        )

        # audit event: three distinct values
        if noop:
            event_type = "tool_execution_noop"
        elif success:
            event_type = "tool_execution_success"
        else:
            event_type = "tool_execution_failed"
        AuditAgent.log(
            ticket_id=ticket_id,
            agent_name="ToolExecutionAgent",
            event_type=event_type,
            details={
                "action_type": action_plan.action_type,
                "target_system": action_plan.target_system,
                "message": result.message,
                "retries": result.retries_attempted
            }
        )

        log.info(
            "ToolExecutionAgent finished",
            ticket_id=ticket_id,
            success=success
        )
        return result
