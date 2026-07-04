"""
supabase_service.py — Basic CRUD wrappers for the Supabase database.

Provides focused functions for interacting with the Supabase REST API via the Python client.
These functions use the service-role client to bypass RLS for backend operations.
"""

import structlog
from typing import Any

from app.database import get_supabase_client  # re-exported for use by policy_engine and other services

log = structlog.get_logger(__name__)


def insert_ticket(ticket_data: dict[str, Any]) -> dict[str, Any]:
    """
    Insert a new ticket into the tickets table.

    Args:
        ticket_data: A dictionary containing the ticket fields to insert.
                     Should align with the normalised ticket dict shape from ITSMClient,
                     but mapped to DB columns (e.g. source, external_id, summary).

    Returns:
        The inserted row as a dict.
    """
    client = get_supabase_client()
    
    # Map the normalized dict from webhook payload to the DB schema
    db_payload = {
        "source": ticket_data.get("source"),
        "external_id": ticket_data.get("external_id"),
        "summary": ticket_data.get("summary"),
        "description": ticket_data.get("description"),
        "status": ticket_data.get("status"),
        "priority": ticket_data.get("priority"),
        # reporter_email is extracted from Jira/ServiceNow webhook payloads
        # and persisted here so ToolExecutionAgent can use it as the send_email recipient.
        "reporter_email": ticket_data.get("reporter_email"),
    }

    log.info("Inserting ticket to Supabase", source=db_payload["source"], external_id=db_payload["external_id"])
    response = client.table("tickets").insert(db_payload).execute()
    
    # Supabase python client execute() returns an APIResponse object.
    # response.data contains the returned rows.
    if not response.data:
        log.error("Failed to insert ticket, no data returned", payload=db_payload)
        raise RuntimeError(f"Failed to insert ticket: {db_payload}")
        
    inserted_row = response.data[0]
    log.info("Ticket inserted successfully", id=inserted_row["id"])
    return inserted_row


def update_ticket(ticket_id: str, ticket_data: dict[str, Any]) -> dict[str, Any]:
    """
    Update an existing ticket by its internal UUID.

    Args:
        ticket_id: The internal UUID of the ticket.
        ticket_data: Dictionary of fields to update.

    Returns:
        The updated row as a dict.
    """
    client = get_supabase_client()
    log.info("Updating ticket in Supabase", id=ticket_id)
    
    response = client.table("tickets").update(ticket_data).eq("id", ticket_id).execute()
    
    if not response.data:
        log.warning("Update ticket returned no data (ticket might not exist)", id=ticket_id)
        return {}
        
    return response.data[0]


def get_ticket_by_id(ticket_id: str) -> dict[str, Any] | None:
    """
    Retrieve a ticket by its internal UUID.

    Args:
        ticket_id: The internal UUID of the ticket.

    Returns:
        The ticket dict if found, else None.
    """
    client = get_supabase_client()
    log.info("Fetching ticket from Supabase", id=ticket_id)
    
    response = client.table("tickets").select("*").eq("id", ticket_id).execute()
    
    if response.data:
        return response.data[0]
    return None


def get_ticket_by_external_id(source: str, external_id: str) -> dict[str, Any] | None:
    """
    Retrieve a ticket by its source and external ID.
    Useful for deduplication during webhook ingestion.

    Args:
        source: "jira" or "servicenow"
        external_id: The external ID (e.g. KAN-123 or INC001)

    Returns:
        The ticket dict if found, else None.
    """
    client = get_supabase_client()
    log.info("Fetching ticket by external ID", source=source, external_id=external_id)
    
    response = client.table("tickets").select("*").eq("source", source).eq("external_id", external_id).execute()
    
    if response.data:
        return response.data[0]
    return None


def list_tickets(limit: int = 100) -> list[dict[str, Any]]:
    """
    List recent tickets.

    Args:
        limit: Maximum number of tickets to return (default 100).

    Returns:
        List of ticket dicts.
    """
    client = get_supabase_client()
    log.info("Listing tickets from Supabase", limit=limit)
    
    response = client.table("tickets").select("*").order("created_at", desc=True).limit(limit).execute()
    
    return response.data


def insert_agent_action(action_data: dict[str, Any]) -> dict[str, Any]:
    """
    Insert a record into the agent_actions table.
    """
    client = get_supabase_client()
    log.info("Inserting agent action", agent=action_data.get("agent_name"), action_type=action_data.get("action_type"))
    response = client.table("agent_actions").insert(action_data).execute()
    return response.data[0] if response.data else {}


def insert_audit_log(log_data: dict[str, Any]) -> dict[str, Any]:
    """
    Insert a record into the append-only audit_logs table.
    """
    client = get_supabase_client()
    log.info("Inserting audit log", audit_event=log_data.get("event_type"))
    response = client.table("audit_logs").insert(log_data).execute()
    return response.data[0] if response.data else {}


def similarity_search_kb(query_embedding: list[float], match_count: int = 5) -> list[dict[str, Any]]:
    """
    Perform a vector similarity search on the knowledge_base table using the match_kb_articles RPC.
    """
    client = get_supabase_client()
    log.info("Performing KB similarity search", match_count=match_count)
    
    # Supabase Python client RPC call
    response = client.rpc(
        "match_kb_articles",
        {"query_embedding": query_embedding, "match_count": match_count}
    ).execute()
    
    return response.data

