from io import BytesIO
import json
from threading import Event
import time

import pytest
from fastapi.testclient import TestClient

from app import qloo
from app.guard import CapacityError, reserve_provider
from app.jobs import JobStore
from app.main import app
from app.runtime import PrivateCache, WorkTimeout, remaining, work_budget


def test_private_cache_is_bounded_and_does_not_expose_mutable_values():
    cache = PrivateCache(capacity=2)
    original = {"value": [1]}
    cache.put("one", original)
    original["value"].append(2)
    assert cache.get("one") == {"value": [1]}
    returned = cache.get("one")
    returned["value"].append(3)
    cache.put("two", 2)
    cache.put("three", 3)
    assert cache.get("one") is None and cache.get("three") == 3


def test_expired_cache_entry_is_not_served(monkeypatch):
    cache = PrivateCache(ttl=1)
    cache.put("key", "value")
    now = time.monotonic()
    monkeypatch.setattr(time, "monotonic", lambda: now + 2)
    assert cache.get("key") is None


def test_provider_cache_is_separated_by_key_and_query(monkeypatch):
    calls = []
    def request(*args, **kwargs):
        calls.append(1)
        return BytesIO(json.dumps({"results": []}).encode())
    monkeypatch.setattr(qloo, "urlopen", request)
    monkeypatch.setattr(qloo.time, "sleep", lambda _: None)
    first, second = qloo.QlooClient("placeholder-one"), qloo.QlooClient("placeholder-two")
    first._get("/search", {"query": "Place"})
    first._get("/search", {"query": "Place"})
    second._get("/search", {"query": "Place"})
    first._get("/search", {"query": "Different"})
    assert len(calls) == 3


def test_timeout_and_nested_cancellation_are_cooperative():
    cancel = Event()
    with work_budget(10, cancellation=cancel):
        with work_budget(10):
            cancel.set()
            with pytest.raises(WorkTimeout, match="cancelled"):
                remaining()
    with pytest.raises(WorkTimeout, match="time limit"):
        with work_budget(0):
            pass


def test_provider_daily_limits_are_enforced_before_another_call(monkeypatch):
    monkeypatch.setenv("RECEIPT_LLM_DAILY_CALLS", "1")
    reserve_provider("llm")
    with pytest.raises(CapacityError, match="daily"):
        reserve_provider("llm")


def test_body_limit_measures_actual_body_and_rate_limit_is_per_address():
    with TestClient(app) as client:
        response = client.post("/api/agent/audit", content=b"x" * 131073)
        assert response.status_code == 413
        for _ in range(60):
            response = client.post("/api/agent/approve", json={"audit_id": "nonexistent"})
            assert response.status_code == 409
        assert client.post("/api/agent/approve", json={"audit_id": "nonexistent"}).status_code == 429


def wait_for_result(client, job_id):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        data = client.get("/api/jobs/" + job_id).json()
        if data["status"] not in ("queued", "running"):
            return data
        time.sleep(0.01)
    raise AssertionError("Job did not finish.")


def test_background_agent_run_keeps_ownership_and_the_final_review_session():
    with TestClient(app) as client:
        response = client.post("/api/jobs/agent", json={
            "anchors": ["Artist", "Film"], "city": "Denver", "mode": "scripted"})
        assert response.status_code == 202
        job_id = response.json()["job_id"]
        data = wait_for_result(client, job_id)
        assert data["status"] == "complete", data
        assert data["result"]["stop_reason"] == "ready_for_review"
        audit_id = data["result"]["final_audit"]["audit_id"]
        assert client.get("/api/review/" + audit_id).status_code == 200
        with TestClient(app) as other:
            assert other.get("/api/jobs/" + job_id).status_code == 404


def test_queued_work_can_be_cancelled_and_does_not_return_a_result():
    store = JobStore()
    started = Event()
    def work():
        started.set()
        while True:
            remaining()
            time.sleep(0.01)
    try:
        job = store.submit("owner", work)
        assert started.wait(timeout=2)
        store.cancel(job["job_id"], "owner")
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            job = store.get(job["job_id"], "owner")
            if job["status"] == "cancelled":
                break
            time.sleep(0.01)
        assert job["status"] == "cancelled" and job["result"] is None
    finally:
        store.pool.shutdown(wait=True)
