from io import BytesIO
import json

import pytest
from fastapi.testclient import TestClient

from app import agent
from app.main import app


def test_scripted_agent_revises_then_gets_a_new_audit(monkeypatch):
    monkeypatch.delenv("QLOO_API_KEY", raising=False)
    with TestClient(app) as client:
        response = client.post("/api/agent/run", json={
            "anchors": ["Kendrick Lamar", "The Bear"], "city": "Denver", "mode": "scripted",
            "constraints": {"category": "restaurant"}})
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["source"]["mode"] == "DEMO"
        assert data["agent"]["label"] == "SCRIPTED DEMO — no LLM"
        assert len(data["rounds"]) == 2
        assert data["stop_reason"] == "ready_for_review"
        assert not data["approval_recorded"]
        first, second = [row["audit"] for row in data["rounds"]]
        assert not first["approval_eligible"] and second["approval_eligible"]
        assert first["comparison_fingerprint"] == second["comparison_fingerprint"]
        review = client.get("/api/review/" + second["audit_id"])
        assert review.status_code == 200


def test_unchanged_agent_is_held_without_a_fake_improvement(monkeypatch):
    monkeypatch.setattr(agent.ScriptedAgent, "revise", lambda self, brief, previous, critique, allowed: previous)
    result = agent.run_loop(anchors=["Artist", "Film"], city="Denver", goal="Dinner",
                            mode="scripted", owner="test")
    assert result["stop_reason"] == "unchanged_or_repeated_list"
    assert len(result["rounds"]) == 1
    assert not result["final_audit"]["approval_eligible"]


def test_live_adapter_requires_explicit_permission_even_if_a_key_exists(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "placeholder")
    monkeypatch.setenv("RECEIPT_LLM_MODEL", "model-for-contract-test")
    monkeypatch.delenv("RECEIPT_ALLOW_LLM_CALLS", raising=False)
    with pytest.raises(agent.AgentError, match="disabled"):
        agent.OpenAIAgent()


@pytest.mark.parametrize("raw", [
    {"recommendations": [], "note": "empty"},
    {"recommendations": ["A", "A"], "note": "duplicate"},
    {"recommendations": ["A"], "note": "ok", "invented_score": 1},
])
def test_invalid_proposals_cannot_enter_the_audit(raw):
    with pytest.raises(agent.AgentError):
        agent.validate_proposal(raw)


def test_revised_agent_cannot_sneak_an_untested_place_into_the_set():
    with pytest.raises(agent.AgentError, match="outside"):
        agent.validate_proposal({"recommendations": ["Unlisted"], "note": "not allowed"}, ["Listed"])


@pytest.fixture
def live_adapter(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "placeholder")
    monkeypatch.setenv("RECEIPT_LLM_MODEL", "model-for-contract-test")
    monkeypatch.setenv("RECEIPT_ALLOW_LLM_CALLS", "1")
    return agent.OpenAIAgent()


def test_responses_adapter_sends_strict_schema_and_checks_completed_output(monkeypatch, live_adapter):
    calls = []
    def response(request, timeout):
        calls.append(json.loads(request.data))
        return BytesIO(json.dumps({"status": "completed", "output": [
            {"type": "message", "content": [{"type": "output_text",
                "text": json.dumps({"recommendations": ["Place"], "note": "Model judgement"})}]}]}).encode())
    monkeypatch.setattr(agent, "urlopen", response)
    proposal = live_adapter.propose({"city": "Denver"})
    assert proposal.recommendations == ["Place"]
    assert calls[0]["store"] is False
    assert calls[0]["text"]["format"]["strict"] is True
    assert calls[0]["max_output_tokens"] == 700


@pytest.mark.parametrize("response", [
    {"status": "incomplete", "output": []},
    {"status": "completed", "output": [{"content": [{"type": "refusal"}]}]},
    {"status": "completed", "output": [{"content": [{"type": "output_text", "text": "not JSON"}]}]},
])
def test_model_refusal_or_bad_output_never_becomes_a_fake_list(monkeypatch, live_adapter, response):
    monkeypatch.setattr(agent, "urlopen", lambda *args, **kwargs: BytesIO(json.dumps(response).encode()))
    with pytest.raises(agent.AgentError):
        live_adapter.propose({"city": "Denver"})


def test_qloo_rules_agent_requires_a_key_without_synthetic_fallback(monkeypatch):
    monkeypatch.delenv("QLOO_API_KEY", raising=False)
    with pytest.raises(agent.AgentError, match="configured Qloo key"):
        agent.QlooDiscoveryAgent()


def test_qloo_rules_agent_revises_real_contract_data_without_model_calls(monkeypatch):
    from app import context
    from app.qloo import Entity, ScoredEntity, normalize_name

    class Graph:
        configured = True
        baseline_verified = False
        restaurant_tag = "urn:tag:category:place:restaurant"

        def __init__(self):
            self.places = [Entity(str(i), name, "urn:entity:place", tags=(self.restaurant_tag,))
                           for i, name in enumerate(["A", "B", "C", "D"] + [f"Reference {i}" for i in range(46)])]

        def configure_scope(self, scope):
            self.scope = scope

        def city_reference_places(self, city):
            return self.places

        def resolve_place(self, name, city):
            return next((p for p in self.places if normalize_name(p.name) == normalize_name(name)), None)

        def resolve_anchor(self, name):
            return Entity("anchor-" + name, name, "urn:entity:artist")

        def score_places(self, anchors, ids, city):
            scores = {"A": .99, "B": .01, "C": .90, "D": .98}
            return [ScoredEntity(**place.__dict__, affinity=scores.get(place.name, .4))
                    for place in self.places if place.entity_id in ids]

        def taste_tags(self, anchors):
            return []

    monkeypatch.setattr(agent, "QlooClient", Graph)
    monkeypatch.setattr(context, "QlooClient", Graph)
    def model_forbidden(*args, **kwargs):
        raise AssertionError("A rules-based Qloo run must never initialize a paid model")
    monkeypatch.setattr(agent.OpenAIAgent, "__init__", model_forbidden)
    with TestClient(app) as client:
        response = client.post("/api/agent/run", json={
            "anchors": ["Artist", "Film"], "city": "Denver", "mode": "qloo",
            "constraints": {"category": "restaurant"}})
        assert response.status_code == 200, response.text
        result = response.json()
        assert result["agent"]["label"] == "LIVE QLOO — generic ratings agent; rules-based, no LLM"
        assert result["source"]["mode"] == "LIVE"
        assert len(result["rounds"]) == 2
        first, changed = [row["audit"] for row in result["rounds"]]
        assert not first["approval_eligible"] and changed["approval_eligible"]
        assert first["comparison_fingerprint"] == changed["comparison_fingerprint"]
        assert result["stop_reason"] == "ready_for_review"
        assert not result["approval_recorded"]
        assert not changed["baseline_available"]
