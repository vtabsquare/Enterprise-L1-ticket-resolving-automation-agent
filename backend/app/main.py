"""
main.py — FastAPI application entry point.

Responsibilities:
  - Create and configure the FastAPI app instance
  - Register all routers
  - Attach startup / shutdown lifecycle hooks
  - Provide /health endpoint
  - Configure structured logging
"""

import sys
import logging
import logging.handlers
from contextlib import asynccontextmanager
from pathlib import Path

import structlog

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.database import check_db_connection
from app.routers import webhook_router, ticket_router, admin_router, dashboard_router

# ── Structured logging setup ──────────────────────────────────────────────────

def configure_logging(log_level: str = "INFO") -> None:
    """
    Configure structlog to write simultaneously to:
      - stdout        (ConsoleRenderer in dev, JSONRenderer in prod)
      - logs/app.log  (RotatingFileHandler, always JSON, 10 MB x 5 backups)

    Uses the structlog stdlib integration so that both stdlib loggers
    (uvicorn, httpx, msal, etc.) and native structlog loggers are routed
    through both sinks.  Every log line in the file is a self-contained JSON
    object — grep-friendly and unambiguous.
    """
    level = getattr(logging, log_level.upper(), logging.INFO)
    settings = get_settings()

    log_file = Path(__file__).resolve().parent.parent / "logs" / "app.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)

    # Processors run on every log event before the renderer ─────────────────
    shared_pre_chain: list = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    # stdout handler ─────────────────────────────────────────────────────────
    console_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer() if settings.is_development
            else structlog.processors.JSONRenderer(),
        ],
        foreign_pre_chain=shared_pre_chain,
    )
    stream_handler = logging.StreamHandler(sys.stdout)
    stream_handler.setFormatter(console_formatter)

    # rotating file handler (always JSON for grep/analysis) ──────────────────
    file_formatter = structlog.stdlib.ProcessorFormatter(
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(),
        ],
        foreign_pre_chain=shared_pre_chain,
    )
    file_handler = logging.handlers.RotatingFileHandler(
        str(log_file),
        maxBytes=10 * 1024 * 1024,  # 10 MB per file
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(file_formatter)

    # Root stdlib logger receives both handlers ───────────────────────────────
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.addHandler(stream_handler)
    root_logger.addHandler(file_handler)
    root_logger.setLevel(level)

    # structlog global configuration ──────────────────────────────────────────
    structlog.configure(
        processors=shared_pre_chain + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
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
