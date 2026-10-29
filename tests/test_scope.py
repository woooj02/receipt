import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.qloo import Entity, QlooClient, QlooError
from app.scope import Scope, Venue, assess, distance_m


TAG = "urn:tag:category:place:restaurant"


def test_distance_is_straight_line_metres():
    assert distance_m(0, 0, 0, 0) == 0
    assert distance_m(0, 0, 1, 0) == pytest.approx(111195, abs=2)


def test_restaurant_and_radius_require_real_metadata():
    scope = Scope("restaurant", Venue("Supplied point", 39.74, -104.99, 1000))
    inside = Entity("a", "A", "urn:entity:place", latitude=39.74, longitude=-104.99, tags=(TAG,))
    outside = Entity("b", "B", "urn:entity:place", latitude=40, longitude=-104.99, tags=(TAG,))
    unknown = Entity("c", "C", "urn:entity:place")
    wrong_category = Entity("d", "D", "urn:entity:place", tags=("urn:tag:category:place:museum",))
    assert assess(inside, scope, TAG) == ("eligible", None, 0)
    assert assess(outside, scope, TAG)[0] == "ineligible"
    assert assess(unknown, scope, TAG)[0] == "unverified"
    assert assess(wrong_category, scope, TAG)[0] == "ineligible"


def test_tag_lookup_and_scoring_use_one_consistent_scope(monkeypatch):
    client = QlooClient("placeholder")
    calls = []
    def get(path, params):
        calls.append((path, params))
        if path == "/v2/tags":
            return {"results": {"tags": [{"tag_id": TAG, "name": "Restaurant"}]}}
        return {"results": {"entities": []}}
    monkeypatch.setattr(client, "_get", get)
    client.configure_scope(Scope("restaurant", Venue("Concert", 39.74, -104.99, 5000)))
    client.city_reference_places("Denver")
    client.score_places(["anchor"], ["a"], "Denver")
    client.score_city_baseline(["a"], "Denver")
    assert calls[0][1]["filter.tag.types"] == "urn:tag:category:place"
    for _, params in calls[1:]:
        assert params["filter.tags"] == TAG
        assert params["filter.location"] == "POINT(-104.99 39.74)"
        assert params["filter.location.radius"] == "5000"
        assert "filter.location.query" not in params


def test_category_is_not_invented_when_tag_lookup_is_ambiguous(monkeypatch):
    client = QlooClient("placeholder")
    monkeypatch.setattr(client, "_get", lambda *args: {"results": {"tags": []}})
    with pytest.raises(QlooError, match="category"):
        client.configure_scope(Scope("restaurant"))


def test_search_uses_live_supported_lat_lon_and_miles(monkeypatch):
    client = QlooClient("placeholder")
    client.scope = Scope("any", Venue("Concert", 39.74, -104.99, 5000))
    calls = []
    monkeypatch.setattr(client, "_get", lambda path, params: calls.append((path, params)) or {"results": []})
    assert client.resolve_place("Example Place", "Denver") is None
    path, params = calls[0]
    assert path == "/search"
    assert params["filter.location"] == "39.74,-104.99"
    assert float(params["filter.radius"]) == pytest.approx(5000 / 1609.344)
    assert "filter.address" not in params


def test_place_parser_preserves_coordinates_and_verified_tag_ids():
    entity = QlooClient()._entity({"entity_id": "a", "name": "A", "types": ["urn:entity:place"],
        "location": {"lat": 39.74, "lon": -104.99},
        "tags": [{"tag_id": TAG}, "not-a-tag", TAG]})
    assert entity.latitude == 39.74 and entity.longitude == -104.99
    assert entity.tags == (TAG,)


def test_scoped_audit_records_distance_and_freezes_constraints(monkeypatch):
    monkeypatch.delenv("QLOO_API_KEY", raising=False)
    data = {"anchors": ["Artist", "Film"], "candidates": ["Juniper House"],
        "city": "Denver", "demo": True,
        "constraints": {"category": "restaurant", "venue": {
            "label": "Demo Concert Hall", "latitude": 39.74, "longitude": -104.99, "radius_m": 5000}}}
    with TestClient(app) as client:
        first = client.post("/api/agent/audit", json=data).json()
        assert first["approval_eligible"]
        assert first["candidates"][0]["distance_m"] is not None
        assert first["constraints"] == data["constraints"]
        data["revision_of"] = first["audit_id"]
        data["candidates"] = ["Cobalt Noodles"]
        data["constraints"]["venue"]["radius_m"] = 1000
        assert client.post("/api/agent/audit", json=data).status_code == 422


def test_outside_radius_is_retained_as_ineligible(monkeypatch):
    monkeypatch.delenv("QLOO_API_KEY", raising=False)
    with TestClient(app) as client:
        response = client.post("/api/agent/audit", json={
            "anchors": ["Artist", "Film"], "candidates": ["Juniper House"], "city": "Denver", "demo": True,
            "constraints": {"venue": {"label": "Far away point", "latitude": 40, "longitude": -104.99, "radius_m": 100}}})
        assert response.status_code == 200
        result = response.json()
        assert result["candidates"][0]["status"] == "ineligible"
        assert result["fixed_universe_count"] == 0
        assert not result["approval_eligible"]
