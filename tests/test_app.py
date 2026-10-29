"""Regression tests for evidence integrity, comparison sets and review confirmation."""

import pytest
from fastapi.testclient import TestClient

from app import context, receipt
from app.main import app
from app.qloo import Entity, QlooError, ScoredEntity


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    monkeypatch.delenv("QLOO_API_KEY", raising=False)
    monkeypatch.delenv("QLOO_BASELINE_VERIFIED", raising=False)
    receipt.PENDING.clear()


@pytest.fixture
def client():
    with TestClient(app) as browser:
        yield browser


def payload(**overrides):
    data = {"anchors": ["Kendrick Lamar", "Everything Everywhere All at Once"],
            "candidates": ["Harbor Street Grill", "Copper Kettle", "Nightjar Lounge"],
            "city": "Denver, Colorado", "demo": True}
    return {**data, **overrides}


def checked_audit(client, **overrides):
    response = client.post("/api/agent/audit", json=payload(**overrides))
    assert response.status_code == 200, response.text
    return response.json()


def confirm(client, result, **changes):
    review = client.get(f'/api/review/{result["audit_id"]}')
    assert review.status_code == 200, review.text
    return client.post("/api/review/approve", json={**review.json(), **changes})


def test_demo_has_real_catalog_unknowns_and_deterministic_scores(client):
    first = checked_audit(client, candidates=["Copper Kettle", "Nightjar Lounge"])
    revision = checked_audit(client, candidates=["Copper Kettle", "Harbor Street Grill"],
                             revision_of=first["audit_id"])
    assert first["source"]["mode"] == "DEMO"
    assert first["candidates"][0]["status"] == revision["candidates"][0]["status"] == "mismatch"
    assert first["candidates"][0]["personal_percentile"] == revision["candidates"][0]["personal_percentile"]
    assert first["comparison_fingerprint"] == revision["comparison_fingerprint"]
    assert not revision["approval_eligible"]
    unknown = checked_audit(client, candidates=["Invented Fixture Restaurant"])
    assert unknown["candidates"][0]["status"] == "unverified"
    assert unknown["candidates"][0]["personal_percentile"] is None


def test_agent_tools_cannot_approve_and_browser_records_exact_confirmation(client):
    result = checked_audit(client, candidates=["Juniper House", "Cobalt Noodles"])
    assert result["approval_eligible"]
    assert client.post("/api/agent/approve", json={"audit_id": result["audit_id"]}).status_code == 409
    assert client.post("/api/review/approve", json={"audit_id": result["audit_id"]}).status_code == 422
    assert confirm(client, result, fingerprint="0" * 64).status_code == 409
    first = confirm(client, result)
    second = confirm(client, result)
    assert first.status_code == 200
    assert first.json() == second.json()  # An approval retry cannot issue a new receipt.
    assert first.json()["approval_recorded"]
    assert not first.json()["approval_identity_verified"]
    assert first.json()["audit_fingerprint"] == result["fingerprint"]


def test_revision_must_pass_fresh_evaluation_and_preserve_context(client):
    first = checked_audit(client)
    assert client.get(f'/api/review/{first["audit_id"]}').status_code == 409
    revised = checked_audit(client, candidates=["Juniper House", "Cobalt Noodles"],
                            revision_of=first["audit_id"])
    assert revised["approval_eligible"]
    assert revised["comparison_fingerprint"] == first["comparison_fingerprint"]
    assert confirm(client, revised).status_code == 200


@pytest.mark.parametrize("change", [
    {"city": "Austin, Texas"}, {"anchors": ["Taylor Swift", "The Bear"]},
    {"policy": "verified_only"}, {"demo": False},
    {"candidates": ["Nightjar Lounge", "Copper Kettle", "Harbor Street Grill"]},
])
def test_revision_cannot_switch_context_or_just_reorder(client, change):
    first = checked_audit(client)
    data = payload(candidates=["Juniper House"], revision_of=first["audit_id"], **change) if "candidates" not in change else payload(revision_of=first["audit_id"], **change)
    response = client.post("/api/agent/audit", json=data)
    assert response.status_code == 422


def test_other_browser_cannot_review_or_revise_an_audit(client):
    result = checked_audit(client, candidates=["Juniper House"])
    with TestClient(app) as other:
        assert other.get(f'/api/review/{result["audit_id"]}').status_code == 409
        response = other.post("/api/agent/audit", json=payload(
            candidates=["Cobalt Noodles"], revision_of=result["audit_id"]))
        assert response.status_code == 422


def test_expired_or_superseded_snapshot_cannot_be_confirmed(client, monkeypatch):
    first = checked_audit(client, candidates=["Juniper House"])
    review = client.get(f'/api/review/{first["audit_id"]}').json()
    changed = checked_audit(client, candidates=["Cobalt Noodles"], revision_of=first["audit_id"])
    assert client.post("/api/review/approve", json=review).status_code == 409
    monkeypatch.setattr(receipt.time, "time", lambda: changed["expires_at"] + 1)
    assert client.get(f'/api/review/{changed["audit_id"]}').status_code == 409


@pytest.mark.parametrize("change", [
    {"anchors": ["Kendrick Lamar", "  "]}, {"anchors": ["Only one"]},
    {"city": "   "}, {"candidates": ["Same Place", "same-place"]},
    {"candidates": ["x" * 201]}, {"policy": "unknown"}, {"extra": True},
])
def test_invalid_inputs_do_not_bypass_normalization_or_bounds(client, change):
    assert client.post("/api/agent/audit", json=payload(**change)).status_code == 422


def test_returned_result_cannot_mutate_stored_evidence():
    result = receipt.audit(**{"anchors": ["A", "B"], "candidates": ["Copper Kettle"],
                              "city": "Denver", "force_demo": True})
    result["approval_eligible"] = True
    result["candidates"][0]["status"] = "supported"
    with pytest.raises(receipt.AuditError):
        receipt.review(result["audit_id"], "local")


class FakeQloo:
    configured = True
    baseline_verified = True
    partial = False
    missing_baseline = False
    reference_calls = 0
    score_universes = []

    def resolve_anchor(self, name):
        return None if name == "Unknown Anchor" else Entity(f"anchor-{name}", name, "urn:entity:artist")

    def resolve_place(self, name, city):
        return None if name == "Unknown Place" else Entity(f"place-{name}", name, "urn:entity:place")

    def city_reference_places(self, city):
        type(self).reference_calls += 1
        return [Entity(f"reference-{index}", f"Reference {index}", "urn:entity:place") for index in range(50)]

    def score_places(self, anchors, ids, city):
        type(self).score_universes.append(tuple(ids))
        rows = [ScoredEntity(item, item, "urn:entity:place",
                0.99 if item == "place-A" else 0.01 if item == "place-B" else 0.5) for item in ids]
        return rows[:1] if self.partial else rows

    def score_city_baseline(self, ids, city):
        rows = [ScoredEntity(item, item, "urn:entity:place", 0.1 if item == "place-A" else 0.5) for item in ids]
        return rows[:1] if self.missing_baseline else rows

    def taste_tags(self, ids):
        return ["Example tag"]


@pytest.fixture
def fake_provider(monkeypatch):
    FakeQloo.reference_calls = 0
    FakeQloo.score_universes = []
    monkeypatch.setattr(context, "QlooClient", FakeQloo)
    return FakeQloo


def test_unresolved_place_stays_in_results_and_cannot_be_approved(client, fake_provider):
    result = checked_audit(client, demo=False, candidates=["A", "Unknown Place"])
    assert len(result["candidates"]) == 2
    assert result["candidates"][0]["status"] == "supported"
    assert result["candidates"][1]["status"] == "unverified"
    assert not result["approval_eligible"]


def test_partial_scores_cannot_promote_one_returned_place(client, fake_provider, monkeypatch):
    monkeypatch.setattr(fake_provider, "partial", True)
    result = checked_audit(client, demo=False, candidates=["A"])
    assert result["scoring_coverage"] == {"scored": 1, "required": 51, "complete": False}
    assert result["candidates"][0]["personal_percentile"] is None
    assert result["candidates"][0]["status"] == "unverified"


def test_sparse_baseline_disables_lift_for_every_place(client, fake_provider, monkeypatch):
    monkeypatch.setattr(fake_provider, "missing_baseline", True)
    result = checked_audit(client, demo=False, candidates=["A", "B"])
    assert not result["baseline_available"]
    assert all(item["taste_lift"] is None for item in result["candidates"])
    assert result["candidates"][1]["status"] == "mismatch"


def test_verified_only_holds_missing_baseline(client, fake_provider, monkeypatch):
    monkeypatch.setattr(fake_provider, "baseline_verified", False)
    result = checked_audit(client, demo=False, candidates=["A"], policy="verified_only")
    assert result["candidates"][0]["status"] == "unverified"


def test_unresolved_anchor_cannot_silently_change_the_profile(client, fake_provider):
    result = checked_audit(client, demo=False, anchors=["Known", "Unknown Anchor"], candidates=["A"])
    assert result["anchors"][1]["resolution"] == "unverified"
    assert result["candidates"][0]["status"] == "unverified"


def test_new_place_in_revision_cannot_change_frozen_universe(client, fake_provider):
    first = checked_audit(client, demo=False, candidates=["A"])
    revised = checked_audit(client, demo=False, candidates=["New Place"], revision_of=first["audit_id"])
    assert revised["comparison_fingerprint"] == first["comparison_fingerprint"]
    assert revised["candidates"][0]["status"] == "unverified"
    assert "outside the frozen" in revised["candidates"][0]["reason"]


def batch_payload(**overrides):
    data = {
        "agent_name": "Caller Supplied Agent", "agent_version": "example-v1",
        "prompt_version": "concert-v1", "captured_at": "2026-10-27T20:00:00Z",
        "city": "Denver", "demo": False,
        "profiles": [
            {"profile_id": "one", "anchors": ["Artist A", "Film A"], "recommendations": ["A", "Unknown Place"]},
            {"profile_id": "two", "anchors": ["Artist B", "Film B"], "recommendations": ["A", "B"]},
        ],
    }
    return {**data, **overrides}


def test_batch_uses_one_shared_universe_and_counts_all_picks(client, fake_provider):
    response = client.post("/api/test-suite", json=batch_payload())
    assert response.status_code == 200, response.text
    data = response.json()
    assert fake_provider.reference_calls == 1
    assert len(set(fake_provider.score_universes)) == 1
    assert len(fake_provider.score_universes[0]) == 52
    assert len({row["comparison_fingerprint"] for row in data["profiles"]}) == 1
    assert data["metrics"]["recommendation_count"] == 4
    assert data["metrics"]["unverified_rate"] == 0.25
    assert data["metrics"]["mismatch_rate"] == 0.25
    assert data["metrics"]["sensitivity"] == pytest.approx(2 / 3)
    assert data["agent"]["provenance"] == "caller_supplied_unverified"


def test_batch_requires_real_timestamp_and_unique_ids(client):
    assert client.post("/api/test-suite", json=batch_payload(captured_at="not-a-date")).status_code == 422
    data = batch_payload()
    data["profiles"][1]["profile_id"] = "one"
    assert client.post("/api/test-suite", json=data).status_code == 422


def test_health_key_presence_is_not_live_verification(client, monkeypatch):
    monkeypatch.setenv("QLOO_API_KEY", "placeholder-for-health-test-only")
    data = client.get("/api/health").json()
    assert data["qloo"] == "configured"
    assert "untested" in data["mode"]


def test_provider_failure_is_not_silently_replaced_with_demo(client, fake_provider, monkeypatch):
    def fail(*args):
        raise QlooError("Provider unavailable.")
    monkeypatch.setattr(fake_provider, "city_reference_places", fail)
    response = client.post("/api/agent/audit", json=payload(demo=False))
    assert response.status_code == 502
    assert "DEMO" not in response.text
