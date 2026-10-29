"""Web, captured-output tests, and agent tools for Receipt."""

from __future__ import annotations

from pathlib import Path
import os
import re
import secrets
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, ValidationError, field_validator
import json

from .batch import run_test_suite
from .qloo import QlooClient, QlooError, normalize_name
from .receipt import AuditError, approve, audit, review
from .agent import AgentError, run_loop
from .guard import CapacityError, RequestGuard, work_slot
from .jobs import JOBS, QueueFull
from .runtime import WorkTimeout, work_budget
from .scope import Scope, Venue

WEB = Path(__file__).resolve().parent.parent / "web"
app = FastAPI(title="Receipt", description="Cultural quality checks for recommendation agents.", version="0.4.0")
app.mount("/static", StaticFiles(directory=WEB), name="static")
app.add_middleware(RequestGuard)

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
City = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=100)]
PolicyID = Literal["standard", "verified_only"]


class InputModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


def distinct(values):
    normalized = list(map(normalize_name, values))
    if not all(normalized) or len(set(normalized)) != len(values):
        raise ValueError("Use nonempty, distinct names.")
    return values


class VenueInput(InputModel):
    label: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False, strict=True)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False, strict=True)
    radius_m: int = Field(default=5000, ge=100, le=50000, strict=True)


class ConstraintInput(InputModel):
    category: Literal["any", "restaurant"] = "any"
    venue: VenueInput | None = None

    def to_scope(self):
        return Scope(self.category, Venue(**self.venue.model_dump()) if self.venue else None)


class AuditRequest(InputModel):
    anchors: list[Name] = Field(min_length=2, max_length=5)
    candidates: list[Name] = Field(min_length=1, max_length=6)
    city: City
    policy: PolicyID = "standard"
    demo: bool = False
    revision_of: str | None = Field(default=None, min_length=8, max_length=100)
    constraints: ConstraintInput = Field(default_factory=ConstraintInput)

    @field_validator("anchors", "candidates")
    @classmethod
    def clean_names(cls, values):
        return distinct(values)


class ApprovalRequest(InputModel):
    audit_id: str = Field(min_length=8, max_length=100)


class BrowserApproval(ApprovalRequest):
    review_token: str = Field(min_length=32, max_length=100)
    fingerprint: str = Field(pattern=r"^[0-9a-f]{64}$")


class CapturedProfile(InputModel):
    profile_id: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]
    anchors: list[Name] = Field(min_length=2, max_length=5)
    recommendations: list[Name] = Field(min_length=1, max_length=6)
    control_group: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)] | None = None

    @field_validator("anchors", "recommendations")
    @classmethod
    def clean_names(cls, values):
        return distinct(values)


class BatchTestRequest(InputModel):
    agent_name: Name
    agent_version: Name
    prompt_version: Name
    captured_at: AwareDatetime
    city: City
    profiles: list[CapturedProfile] = Field(min_length=2, max_length=20)
    policy: PolicyID = "standard"
    demo: bool = False
    constraints: ConstraintInput = Field(default_factory=ConstraintInput)

    @field_validator("profiles")
    @classmethod
    def unique_profile_ids(cls, profiles):
        if len({profile.profile_id.casefold() for profile in profiles}) != len(profiles):
            raise ValueError("Use unique profile IDs.")
        controls = {}
        for profile in profiles:
            if profile.control_group:
                tastes = frozenset(map(normalize_name, profile.anchors))
                if profile.control_group in controls and controls[profile.control_group] != tastes:
                    raise ValueError("Repeat controls must keep the same tastes.")
                controls[profile.control_group] = tastes
        return profiles


class AgentRunRequest(InputModel):
    anchors: list[Name] = Field(min_length=2, max_length=5)
    city: City
    goal: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1000)] = "Pre-show dinner"
    mode: Literal["scripted", "qloo", "live"] = "scripted"
    policy: PolicyID = "standard"
    max_rounds: int = Field(default=3, ge=1, le=3)
    constraints: ConstraintInput = Field(default_factory=ConstraintInput)

    @field_validator("anchors")
    @classmethod
    def unique_anchors(cls, values):
        return distinct(values)


@app.middleware("http")
async def browser_session(request: Request, call_next):
    session_id = request.cookies.get("receipt_session", "")
    fresh = not re.fullmatch(r"[A-Za-z0-9_-]{43}", session_id)
    request.state.receipt_session = secrets.token_urlsafe(32) if fresh else session_id
    response = await call_next(request)
    response.set_cookie("receipt_session", request.state.receipt_session,
                            httponly=True, samesite="strict", secure=request.url.scheme == "https",
                            max_age=1800)
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'"
    return response


@app.get("/")
def index():
    return FileResponse(WEB / "receipt.html", headers={"Cache-Control": "no-cache"})


@app.get("/api/health")
def health():
    configured = QlooClient().configured
    return {"ok": True, "qloo": "configured" if configured else "demo",
            "mode": "Qloo configured · connection untested" if configured else "DEMO — SYNTHETIC",
            "agent_endpoint": "/api/agent/audit", "test_suite_endpoint": "/api/test-suite",
            "jobs_endpoint": "/api/jobs/{kind}", "agent_loop_endpoint": "/api/agent/run",
            "qloo_agent_enabled": configured,
            "live_agent_enabled": (os.environ.get("RECEIPT_ALLOW_LLM_CALLS") == "1"
                                   and bool(os.environ.get("RECEIPT_LLM_MODEL"))
                                   and bool(os.environ.get("OPENAI_API_KEY")) and configured)}


@app.exception_handler(CapacityError)
async def capacity_error(request, exc):
    return JSONResponse(status_code=429, content={"detail": str(exc)}, headers={"Retry-After": "60"})


@app.exception_handler(WorkTimeout)
async def timeout_error(request, exc):
    return JSONResponse(status_code=504, content={"detail": str(exc)})


@app.exception_handler(AgentError)
async def model_error(request, exc):
    return JSONResponse(status_code=503, content={"detail": str(exc)})


def _execute(kind, payload, owner):
    with work_slot(), work_budget(180):
        if kind == "audit":
            return audit(anchors=payload.anchors, candidates=payload.candidates, city=payload.city,
                         policy=payload.policy, force_demo=payload.demo, revision_of=payload.revision_of,
                         owner=owner, scope=payload.constraints.to_scope())
        if kind == "agent":
            return run_loop(anchors=payload.anchors, city=payload.city, goal=payload.goal,
                            mode=payload.mode, owner=owner, policy=payload.policy,
                            scope=payload.constraints.to_scope(), max_rounds=payload.max_rounds)
        agent = {"name": payload.agent_name, "version": payload.agent_version,
                 "prompt_version": payload.prompt_version, "captured_at": payload.captured_at.isoformat(),
                 "provenance": "caller_supplied_unverified"}
        return run_test_suite(agent=agent, city=payload.city, profiles=[p.model_dump() for p in payload.profiles],
                              force_demo=payload.demo, policy=payload.policy, scope=payload.constraints.to_scope())


@app.post("/api/agent/audit")
def agent_audit(payload: AuditRequest, request: Request):
    """Audit local-place proposals. Preserve the session cookie for revisions."""
    try:
        return _execute("audit", payload, request.state.receipt_session)
    except AuditError as exc:
        raise HTTPException(422, str(exc)) from exc
    except QlooError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/api/agent/approve", deprecated=True)
def refuse_agent_approval(payload: ApprovalRequest):
    raise HTTPException(409, "Agent tools cannot record approval. Use the browser review flow.")


@app.get("/api/review/{audit_id}", include_in_schema=False)
def browser_review(audit_id: str, request: Request):
    try:
        return review(audit_id, request.state.receipt_session)
    except AuditError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/review/approve", include_in_schema=False)
def browser_approve(payload: BrowserApproval, request: Request):
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != str(request.base_url).rstrip("/"):
        raise HTTPException(403, "Review must come from this application's origin.")
    try:
        return approve(payload.audit_id, owner=request.state.receipt_session,
                       review_token=payload.review_token, fingerprint=payload.fingerprint)
    except AuditError as exc:
        raise HTTPException(409, str(exc)) from exc


@app.post("/api/test-suite")
def test_suite(payload: BatchTestRequest, request: Request):
    """Evaluate caller-supplied outputs; capture provenance is not independently verified."""
    try:
        return _execute("batch", payload, request.state.receipt_session)
    except AuditError as exc:
        raise HTTPException(422, str(exc)) from exc
    except QlooError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/api/agent/run")
def agent_run(payload: AgentRunRequest, request: Request):
    try:
        return _execute("agent", payload, request.state.receipt_session)
    except AuditError as exc:
        raise HTTPException(422, str(exc)) from exc
    except QlooError as exc:
        raise HTTPException(502, str(exc)) from exc


@app.post("/api/jobs/{kind}", status_code=202)
def start_job(kind: Literal["audit", "batch", "agent"], payload: dict, request: Request):
    models = {"audit": AuditRequest, "batch": BatchTestRequest, "agent": AgentRunRequest}
    try:
        parsed = models[kind].model_validate(payload)
    except ValidationError as exc:
        raise HTTPException(422, json.loads(exc.json(include_url=False))) from exc
    owner = request.state.receipt_session
    try:
        return JOBS.submit(owner, lambda: _execute(kind, parsed, owner))
    except QueueFull as exc:
        raise HTTPException(429, str(exc)) from exc


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str, request: Request):
    try:
        return JOBS.get(job_id, request.state.receipt_session)
    except KeyError as exc:
        raise HTTPException(404, "Run not found in this session.") from exc


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str, request: Request):
    try:
        return JOBS.cancel(job_id, request.state.receipt_session)
    except KeyError as exc:
        raise HTTPException(404, "Run not found in this session.") from exc
