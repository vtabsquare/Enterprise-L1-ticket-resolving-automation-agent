"""
main.py — FastAPI application entry point.

Responsibilities:
  - Create and configure the FastAPI app instance
  - Register all routers
  - Attach startup / shutdown lifecycle hooks
  - Provide /health endpoint
  - Configure structured logging
"""

import structlog
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import check_db_connection
from app.routers import webhook_router, ticket_router, admin_router, dashboard_router

# ── Structured logging setup ──────────────────────────────────────────────────

def configure_logging(log_level: str = "INFO") -> None:
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.dev.ConsoleRenderer() if get_settings().is_development
            else structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, log_level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
    )


log = structlog.get_logger(__name__)


# ── Lifespan (startup + shutdown) ─────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Runs once on startup; cleanup runs on shutdown."""
    settings = get_settings()
    configure_logging(settings.log_level)

    log.info(
        "L1 Automation Platform starting",
        env=settings.app_env,
        servicenow_mode=settings.servicenow_mode,
    )

    # Verify DB connectivity at startup (non-fatal — allows degraded boot)
    db_ok = check_db_connection()
    if not db_ok:
        log.warning("Database connection check failed at startup — continuing in degraded mode")

    yield  # ← application runs here

    log.info("L1 Automation Platform shutting down")


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Enterprise Agentic AI L1 Support Automation Platform",
        description=(
            "Automates Level-1 IT support tickets via a multi-agent pipeline: "
            "intake → classification → RAG → planning → policy → execution → audit."
        ),
        version="0.1.0",
        docs_url="/api/docs" if not settings.is_production else None,
        redoc_url="/api/redoc" if not settings.is_production else None,
        openapi_url="/api/openapi.json" if not settings.is_production else None,
        lifespan=lifespan,
    )

    # ── CORS (dashboard React app) ────────────────────────────────────────────
    # Restrict in production to your actual dashboard origin
    origins = (
        ["*"]
        if settings.is_development
        else ["https://your-dashboard-domain.example.com"]
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["*"],
    )

    # ── Routers ───────────────────────────────────────────────────────────────
    app.include_router(webhook_router.router, prefix="/api/webhooks", tags=["Webhooks"])
    app.include_router(ticket_router.router,  prefix="/api/tickets",  tags=["Tickets"])
    app.include_router(admin_router.router,   prefix="/api/admin",    tags=["Admin"])
    app.include_router(dashboard_router.router, prefix="/api/dashboard", tags=["Dashboard"])

    # ── Health endpoint ───────────────────────────────────────────────────────
    @app.get("/health", tags=["Health"], summary="Platform health check")
    async def health():
        """
        Returns connectivity status for the database and Redis.
        Used by Docker health checks, load balancers, and monitoring.
        """
        import redis as redis_lib
        settings = get_settings()

        db_ok = check_db_connection()

        try:
            r = redis_lib.from_url(settings.redis_url, socket_timeout=2)
            r.ping()
            redis_ok = True
        except Exception:
            redis_ok = False

        overall = "healthy" if (db_ok and redis_ok) else "degraded"
        status_code = 200 if overall == "healthy" else 503

        return JSONResponse(
            status_code=status_code,
            content={
                "status": overall,
                "database": db_ok,
                "redis": redis_ok,
                "version": "0.1.0",
            },
        )

    return app


# ── Entry point ───────────────────────────────────────────────────────────────
app = create_app()
