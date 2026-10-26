"""FastAPI application for SQLBuddy's local web interface."""

import base64
import binascii
import hmac
import logging
import sqlite3
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import HistoryStore
from .models import Answer, QueryRequest, QueryResponse, RenameSessionRequest, SchemaInput, SessionDetail, SessionSummary
from .rate_limit import RateLimiter
from .service import ServiceError, generate_answer

logging.basicConfig(level=getattr(logging, settings.log_level, logging.INFO))
logger = logging.getLogger(__name__)


def has_valid_access_password(authorization: str, expected_password: str) -> bool:
    """Check one Basic authorization header without logging its contents."""
    if not authorization.startswith("Basic "):
        return False
    try:
        decoded = base64.b64decode(authorization[6:], validate=True).decode("utf-8")
        username, separator, password = decoded.partition(":")
    except (binascii.Error, UnicodeDecodeError):
        return False
    return (
        separator == ":"
        and username == "sqlbuddy"
        and hmac.compare_digest(password.encode("utf-8"), expected_password.encode("utf-8"))
    )


def validate_access_password_config(required: bool, password: str) -> None:
    """Fail at startup if a public deployment would be left unprotected."""
    if required and len(password) < 16:
        raise RuntimeError(
            "SQLBUDDY_ACCESS_PASSWORD must be at least 16 characters when "
            "SQLBUDDY_REQUIRE_ACCESS_PASSWORD is enabled."
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    validate_access_password_config(
        settings.require_access_password, settings.access_password
    )
    store = HistoryStore(settings.database_path)
    store.initialize()
    app.state.history = store
    app.state.answer_generator = generate_answer
    yield


app = FastAPI(
    title="SQLBuddy API",
    description="Local API for read-only SQL suggestions and saved query history.",
    version="1.0.0",
    lifespan=lifespan,
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
app.add_middleware(RateLimiter, settings.rate_limit_requests, settings.rate_limit_window_seconds)


@app.middleware("http")
async def require_access_password(request: Request, call_next):
    """Protect API data and Gemini usage in public deployments with Basic auth."""
    if (
        settings.require_access_password
        and request.url.path.startswith("/api/v1/")
        and request.url.path != "/api/v1/health"
        and request.method != "OPTIONS"
    ):
        authorization = request.headers.get("authorization", "")
        if not has_valid_access_password(authorization, settings.access_password):
            return JSONResponse(
                status_code=401,
                content={"error": {"code": "authentication_required", "message": "Enter the SQLBuddy access password."}},
            )
    return await call_next(request)


@app.exception_handler(ServiceError)
async def service_error_handler(_request: Request, exc: ServiceError):
    return JSONResponse(status_code=exc.status_code, content={"error": {"code": exc.code, "message": exc.message}})


@app.exception_handler(RequestValidationError)
async def validation_error_handler(_request: Request, exc: RequestValidationError):
    details = [
        {"field": ".".join(str(part) for part in error["loc"] if part != "body"),
         "message": error["msg"]}
        for error in exc.errors()
    ]
    return JSONResponse(
        status_code=422,
        content={"error": {"code": "invalid_request", "message": "Please check the request fields and try again.", "details": details}},
    )


@app.exception_handler(sqlite3.Error)
async def database_error_handler(_request: Request, _exc: sqlite3.Error):
    logger.exception("SQLBuddy history database operation failed")
    return JSONResponse(status_code=503, content={"error": {"code": "history_unavailable", "message": "Saved history is temporarily unavailable."}})


@app.get("/api/v1/health")
def health(request: Request):
    """Report service and history availability without exposing secrets."""
    available = request.app.state.history.check()
    return JSONResponse(status_code=200 if available else 503, content={"status": "ok" if available else "degraded", "history": "available" if available else "unavailable"})


@app.get("/api/v1/auth/check")
def check_authentication():
    """Confirm the caller supplied the configured access password."""
    return {"authenticated": True}


@app.post("/api/v1/queries", response_model=QueryResponse, status_code=201)
def create_query(payload: QueryRequest, request: Request):
    """Generate one answer and persist it in the selected history session."""
    if len(payload.question) > settings.max_question_chars:
        return JSONResponse(status_code=413, content={"error": {"code": "question_too_large", "message": "The question is too long."}})
    schema_text = payload.schema_context.model_dump_json() if payload.schema_context else ""
    if len(schema_text) > settings.max_schema_chars:
        return JSONResponse(status_code=413, content={"error": {"code": "schema_too_large", "message": "The schema details are too large."}})
    answer: Answer = request.app.state.answer_generator(payload)
    try:
        session_id, created_at = request.app.state.history.add_message(payload.session_id, payload.question, answer.model_dump(), payload.dialect)
    except KeyError:
        return JSONResponse(status_code=404, content={"error": {"code": "session_not_found", "message": "Saved session was not found."}})
    return QueryResponse(session_id=session_id, answer=answer, dialect=payload.dialect, created_at=datetime.fromisoformat(created_at))


@app.get("/api/v1/sessions", response_model=list[SessionSummary])
def list_sessions(request: Request):
    return request.app.state.history.list_sessions()


@app.get("/api/v1/sessions/{session_id}", response_model=SessionDetail)
def get_session(session_id: UUID, request: Request):
    session = request.app.state.history.get_session(session_id)
    if session is None:
        return JSONResponse(status_code=404, content={"error": {"code": "session_not_found", "message": "Saved session was not found."}})
    return session


@app.patch("/api/v1/sessions/{session_id}", response_model=SessionSummary)
def rename_session(session_id: UUID, payload: RenameSessionRequest, request: Request):
    if not request.app.state.history.rename_session(session_id, payload.title):
        return JSONResponse(status_code=404, content={"error": {"code": "session_not_found", "message": "Saved session was not found."}})
    return next(session for session in request.app.state.history.list_sessions() if session["id"] == str(session_id))


@app.delete("/api/v1/sessions/{session_id}", status_code=204)
def delete_session(session_id: UUID, request: Request):
    if not request.app.state.history.delete_session(session_id):
        return JSONResponse(status_code=404, content={"error": {"code": "session_not_found", "message": "Saved session was not found."}})
    return None


@app.get("/api/v1/schema/example", response_model=SchemaInput)
def schema_example():
    """Return a small example schema to help format optional context."""
    return SchemaInput.model_validate({"tables": [{"name": "users", "columns": ["id", "email", "created_at"]}]})


# Production Docker images include the built frontend. Local development uses Vite.
frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
