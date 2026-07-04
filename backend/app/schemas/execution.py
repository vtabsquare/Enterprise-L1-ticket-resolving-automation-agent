"""
execution.py — Pydantic schemas for the Tool Execution step.
"""

from typing import Any
from pydantic import BaseModel, Field

class ExecutionResult(BaseModel):
    success: bool = Field(
        ..., 
        description="True if the tool executed successfully, False otherwise."
    )
    message: str = Field(
        ..., 
        description="Human-readable success or failure message."
    )
    raw_response: dict[str, Any] | None = Field(
        default=None, 
        description="Raw API response for debugging."
    )
    retries_attempted: int = Field(
        default=0, 
        description="Number of times the tool retried before giving up."
    )
