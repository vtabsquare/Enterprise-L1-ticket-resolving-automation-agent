"""
Fault-injection check for ClassificationAgent's Supabase ticket fetch retry.

This script intentionally avoids real Supabase/Gemini dependencies. It imports
the actual repo code for agent_utils.py and classification_agent.py, then stubs
their external dependencies so bundled Python can execute it in the sandbox.
"""

from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class _Logger:
    def __init__(self, name: str = "") -> None:
        self.name = name

    def bind(self, **kwargs):
        return self

    def info(self, event: str, **kwargs) -> None:
        print({"level": "info", "event": event, **kwargs})

    def warning(self, event: str, **kwargs) -> None:
        print({"level": "warning", "event": event, **kwargs})

    def error(self, event: str, **kwargs) -> None:
        print({"level": "error", "event": event, **kwargs})


structlog = types.ModuleType("structlog")
structlog.get_logger = lambda name=None: _Logger(name or "")
sys.modules["structlog"] = structlog

app = types.ModuleType("app")
agents = types.ModuleType("app.agents")
services = types.ModuleType("app.services")
sys.modules["app"] = app
sys.modules["app.agents"] = agents
sys.modules["app.services"] = services


calls = {"get_ticket_by_id": 0, "update_ticket": 0, "insert_agent_action": 0}


def get_ticket_by_id(ticket_id: str) -> dict:
    calls["get_ticket_by_id"] += 1
    if calls["get_ticket_by_id"] == 1:
        raise OSError(10035, "A non-blocking socket operation could not be completed immediately")
    return {
        "id": ticket_id,
        "summary": "Cannot connect to VPN",
        "description": "VPN login fails after password change",
    }


def update_ticket(ticket_id: str, data: dict) -> dict:
    calls["update_ticket"] += 1
    return {"id": ticket_id, **data}


def insert_agent_action(payload: dict) -> dict:
    calls["insert_agent_action"] += 1
    return {"id": "agent-action-1", **payload}


supabase_service = types.ModuleType("app.services.supabase_service")
supabase_service.get_ticket_by_id = get_ticket_by_id
supabase_service.update_ticket = update_ticket
supabase_service.insert_agent_action = insert_agent_action
services.supabase_service = supabase_service
sys.modules["app.services.supabase_service"] = supabase_service


class _Gemini:
    def classify_ticket(self, summary: str, description: str | None) -> dict:
        return {"category": "vpn_connectivity_issue", "confidence": 0.97}


gemini_service = types.ModuleType("app.services.gemini_service")
gemini_service.get_gemini_service = lambda: _Gemini()
sys.modules["app.services.gemini_service"] = gemini_service


class _AuditAgent:
    @staticmethod
    def log(**kwargs) -> None:
        print({"level": "info", "event": "AuditAgent.log", **kwargs})


audit_agent = types.ModuleType("app.agents.audit_agent")
audit_agent.AuditAgent = _AuditAgent
sys.modules["app.agents.audit_agent"] = audit_agent


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


_load_module("app.agents.agent_utils", ROOT / "app" / "agents" / "agent_utils.py")
classification_agent = _load_module(
    "app.agents.classification_agent",
    ROOT / "app" / "agents" / "classification_agent.py",
)

result = classification_agent.ClassificationAgent.process("fault-injection-ticket")

print({"result": result, "calls": calls})

if calls["get_ticket_by_id"] != 2:
    raise SystemExit("Expected get_ticket_by_id to be called exactly twice")
if result["category"] != "vpn_connectivity_issue":
    raise SystemExit("Expected ClassificationAgent to continue after retry")

print("CLASSIFICATION_RETRY_VERIFIED")
