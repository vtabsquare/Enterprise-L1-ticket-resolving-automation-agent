# Enterprise L1 Ticket Resolving Automation Agent

This repository contains the backend and frontend code for an Agentic AI L1 IT Helpdesk Automation Platform. It autonomously intercepts, classifies, plans, and executes IT support tickets using Google Gemini 1.5, Microsoft Graph API, ServiceNow/Jira, and a robust policy engine.

## Features
- **Intake & Orchestration**: Webhook listeners to instantly ingest Jira/ServiceNow tickets.
- **AI Classification**: Categorizes tickets with high accuracy using Few-Shot prompting.
- **Knowledge Base RAG**: Retrieves relevant resolution articles to guide LLM-based troubleshooting.
- **Policy Engine**: A strict rules-based layer that enforces execution permissions (e.g., auto-resolve vs escalate) preventing rogue AI actions.
- **Tool Execution**: Integrates directly with Microsoft Graph (for AD unlocks, group modifications, etc.).
- **Dashboard**: A React frontend to view real-time metrics, audit logs, and policy decisions.

## Required Environment Variables
The application relies on a strictly typed configuration file (`app/config.py`). It expects a `.env` file at the root level of the backend directory or project root.

Please copy `.env.example` to `.env` and fill in your actual credentials.
```bash
cp .env.example .env
```
Key required variables include:
- **Supabase**: `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`
- **Gemini**: `GEMINI_API_KEY`
- **ITSM (Jira/ServiceNow)**: E.g., `JIRA_BASE_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`
- **Microsoft Graph**: `MS_TENANT_ID`, `MS_CLIENT_ID`, `MS_CLIENT_SECRET`

## Running Locally

### Backend (FastAPI)
```bash
cd backend
python -m venv venv
# Windows: venv\Scripts\activate | Mac/Linux: source venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```
### Frontend (React/Vite)
```bash
cd dashboard
npm install
npm run dev
```

## Deployment Notes (Render & Docker)
The repository contains a production-ready `Dockerfile` optimized for Render or other container-hosting platforms.

- The `Dockerfile` **does not** copy the `.env` file into the image. You must inject environment variables securely via your hosting provider (e.g., Render Environment Variables settings).
- **Start Command**: The Docker container automatically runs `uvicorn app.main:app --host 0.0.0.0 --port 8000`.
- **Database**: Ensure that your Supabase instance is accessible from your deployment provider.
- **Webhooks**: After deploying, remember to update Jira/ServiceNow webhook configurations to point to your new public Render URL.
