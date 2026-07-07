import pytest
import os
import sys
import time
import requests
from requests.auth import HTTPBasicAuth
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
load_dotenv('.env')

from app.services.graph_service import GraphService
from app.services.supabase_service import get_supabase_client


def pytest_configure(config):
    """Safeguard: fail loudly if running in parallel without loadgroup mode."""
    if hasattr(config.option, "numprocesses") and config.option.numprocesses:
        dist = getattr(config.option, "dist", None)
        if dist not in ("loadgroup", "loadfile"):
            pytest.exit("ERROR: These integration tests share state and MUST run serially. "
                        "If using xdist, you must run with --dist=loadgroup.")


class TestJiraClient:
    def __init__(self):
        self.url = os.environ["JIRA_BASE_URL"].rstrip("/")
        self.user = os.environ["JIRA_EMAIL"]
        self.token = os.environ["JIRA_API_TOKEN"]
        self.project = os.environ.get("JIRA_PROJECT_KEY", "KAN")
        self.auth = HTTPBasicAuth(self.user, self.token)
        self.headers = {"Accept": "application/json", "Content-Type": "application/json"}

    def create_test_ticket(self, summary: str, description: str) -> str:
        payload = {
            "fields": {
                "project": {"key": self.project},
                "summary": f"[TEST] {summary}",
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [{"type": "paragraph", "content": [{"type": "text", "text": description}]}]
                },
                "issuetype": {"name": "Task"}
            }
        }
        resp = requests.post(f"{self.url}/rest/api/3/issue", json=payload, headers=self.headers, auth=self.auth)
        if resp.status_code != 201:
            raise RuntimeError(f"Failed to create Jira ticket: {resp.text}")
        return resp.json()["key"]

    def delete_ticket(self, issue_key: str):
        resp = requests.delete(f"{self.url}/rest/api/3/issue/{issue_key}", headers=self.headers, auth=self.auth)
        if resp.status_code != 204:
            raise RuntimeError(f"Failed to delete ticket {issue_key}: {resp.text}")

    def update_summary(self, issue_key: str, summary: str):
        payload = {"fields": {"summary": summary}}
        requests.put(f"{self.url}/rest/api/3/issue/{issue_key}", json=payload, headers=self.headers, auth=self.auth)

@pytest.fixture(scope="session")
def graph_client():
    return GraphService()

@pytest.fixture(scope="session")
def jira_client():
    return TestJiraClient()

@pytest.fixture(scope="session")
def supabase_client():
    return get_supabase_client()

@pytest.fixture
def wait_for_ticket_completion():
    def _wait(supabase_client, issue_key: str, timeout: int = 45, poll_interval: int = 2):
        start_time = time.time()
        while time.time() - start_time < timeout:
            res = supabase_client.table("tickets").select("*").eq("external_id", issue_key).execute()
            if res.data:
                ticket = res.data[0]
                if ticket["status"] in ["resolved", "escalated"]:
                    return ticket
            time.sleep(2)
        raise TimeoutError(f"Ticket {issue_key} did not complete within {timeout}s")
    return _wait
