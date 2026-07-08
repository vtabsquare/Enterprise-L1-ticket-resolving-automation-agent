"""
orchestrator.py — The master pipeline that chains all agents together.
"""

import structlog

from app.services import supabase_service
from app.agents.intake_agent import IntakeAgent
from app.agents.classification_agent import ClassificationAgent
from app.agents.knowledge_agent import KnowledgeAgent
from app.agents.planning_agent import PlanningAgent
from app.services import policy_engine
from app.agents.tool_execution_agent import ToolExecutionAgent
from app.agents.ticket_update_agent import TicketUpdateAgent
from app.agents.escalation_agent import EscalationAgent
from app.agents.agent_utils import retry_once

log = structlog.get_logger(__name__)

class Orchestrator:
    """
    Executes the full ticket lifecycle pipeline:
    Classification -> Knowledge -> Planning -> Policy -> Execute/Escalate
    """

    @staticmethod
    def process_ticket(ticket_id: str) -> None:
        """
        Runs the end-to-end pipeline for an already-ingested ticket.
        """
        log.info("Orchestrator starting pipeline", ticket_id=ticket_id)

        try:
            # 1. Classification
            classification = ClassificationAgent.process(ticket_id)

            # 2. Knowledge
            # We don't need to pass category here as KnowledgeAgent fetches the ticket itself
            kb_context = KnowledgeAgent.retrieve_context(ticket_id)

            # 3. Planning
            action_plan = PlanningAgent.process(ticket_id, classification, kb_context)

            # Fetch full ticket to pass to PolicyEngine
            ticket = retry_once(
                lambda: supabase_service.get_ticket_by_id(ticket_id),
                agent="Orchestrator", ticket_id=ticket_id, call="Supabase get_ticket_by_id",
            )
            if not ticket:
                log.error("Ticket not found in orchestrator", ticket_id=ticket_id)
                return

            # 4. Policy Engine Gate
            decision = policy_engine.evaluate(action_plan, ticket)

            # 5. Branch based on Policy Decision
            if decision.is_approved:
                # Execute the approved plan
                execution_result = ToolExecutionAgent.execute(ticket_id, action_plan)

                # Check execution success
                if execution_result.success:
                    # Resolve ticket
                    TicketUpdateAgent.resolve_ticket(ticket_id, execution_result)
                else:
                    # Escalate due to execution failure
                    EscalationAgent.escalate(
                        ticket_id,
                        reason=f"Auto-execution failed: {execution_result.message}"
                    )

            else:
                # Plan was BLOCKED or ESCALATED by Policy Engine
                # We escalate both to human queue for manual handling
                EscalationAgent.escalate(ticket_id, reason=decision.reason)

            log.info("Orchestrator finished pipeline successfully", ticket_id=ticket_id)

        except Exception as e:
            log.error("Orchestrator pipeline failed", ticket_id=ticket_id, error=str(e))
            # Fallback escalation if something catastrophically failed mid-pipeline
            try:
                EscalationAgent.escalate(ticket_id, reason=f"Pipeline exception: {str(e)}")
            except Exception as esc_e:
                log.error("Fallback escalation also failed", ticket_id=ticket_id, error=str(esc_e))
