"""
test_agents.py — Standalone script to test Classification and Knowledge agents.

Usage:
    python -m scripts.test_agents <ticket_id>
"""

import sys
import os
import json
import structlog

# Add backend directory to sys.path so we can import app modules
backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, backend_dir)

from app.agents.classification_agent import ClassificationAgent
from app.agents.knowledge_agent import KnowledgeAgent

log = structlog.get_logger(__name__)

def main():
    if len(sys.argv) < 2:
        print("Usage: python -m scripts.test_agents <ticket_id>")
        sys.exit(1)

    ticket_id = sys.argv[1]

    print(f"\n{'='*50}")
    print(f"Testing Agents on Ticket: {ticket_id}")
    print(f"{'='*50}\n")

    # 1. Test ClassificationAgent
    print("--- 1. ClassificationAgent ---")
    try:
        classification = ClassificationAgent.process(ticket_id)
        print("Result:")
        print(json.dumps(classification, indent=2))
    except Exception as e:
        print(f"Failed to run ClassificationAgent: {e}")

    print("\n--- 2. KnowledgeAgent ---")
    try:
        kb_matches = KnowledgeAgent.retrieve_context(ticket_id)
        if not kb_matches:
            print("No KB matches found.")
        else:
            print(f"Found {len(kb_matches)} matches:")
            for i, match in enumerate(kb_matches, 1):
                title = match.get("title", "Unknown")
                similarity = match.get("similarity", 0.0)
                print(f"  {i}. {title} (Similarity: {similarity:.4f})")
    except Exception as e:
        print(f"Failed to run KnowledgeAgent: {e}")

    print(f"\n{'='*50}")
    print("Test complete.")

if __name__ == "__main__":
    main()
