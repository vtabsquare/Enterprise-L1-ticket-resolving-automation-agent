"""
test_planning.py — Standalone script to test PlanningAgent and PolicyEngine.

Usage:
    python -m scripts.test_planning <ticket_id>
"""

import sys
import os
import json
import structlog

# Add backend directory to sys.path
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from app.services import supabase_service
from app.agents.classification_agent import ClassificationAgent
from app.agents.knowledge_agent import KnowledgeAgent
from app.agents.planning_agent import PlanningAgent
from app.services import policy_engine

log = structlog.get_logger(__name__)

def main():
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.test_planning <ticket_id>")
        sys.exit(1)

    ticket_id = sys.argv[1]

    print(f"\n{'='*60}")
    print(f"Testing Planning & Policy Engine on Ticket: {ticket_id}")
    print(f"{'='*60}\n")
    
    # 0. Fetch raw ticket
    ticket = supabase_service.get_ticket_by_id(ticket_id)
    if not ticket:
        print(f"Error: Ticket {ticket_id} not found in database.")
        sys.exit(1)

    # 1. Run upstream agents (Classification + Knowledge)
    print("--- 1. Running Upstream Context ---")
    classification = ClassificationAgent.process(ticket_id)
    kb_context = KnowledgeAgent.retrieve_context(ticket_id)
    print(f"Category: {classification.get('category')} (Confidence: {classification.get('confidence')})")
    print(f"KB Context: {len(kb_context)} articles retrieved.\n")

    # 2. Run PlanningAgent
    print("--- 2. PlanningAgent Output ---")
    try:
        action_plan = PlanningAgent.process(ticket_id, classification, kb_context)
        print(json.dumps(action_plan.model_dump(), indent=2))
    except Exception as e:
        print(f"Failed to run PlanningAgent: {e}")
        sys.exit(1)

    # 3. Run PolicyEngine
    print("\n--- 3. PolicyEngine Decision ---")
    try:
        # We must refetch ticket because ClassificationAgent mutated it in the DB
        updated_ticket = supabase_service.get_ticket_by_id(ticket_id)
        
        decision = policy_engine.evaluate(action_plan, updated_ticket)
        print(f"Outcome: {decision.outcome.value.upper()}")
        print(f"Reason:  {decision.reason}")
        if decision.policy_id:
            print(f"Matched Policy ID: {decision.policy_id}")
        if decision.escalation_target:
            print(f"Escalating to: {decision.escalation_target}")
            
    except Exception as e:
        print(f"Failed to run PolicyEngine: {e}")
        sys.exit(1)

    print(f"\n{'='*60}")
    print("Test complete.")

if __name__ == "__main__":
    main()
