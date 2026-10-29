from io import BytesIO
from urllib.error import HTTPError

import pytest

from app import qloo
from app.qloo import QlooClient, QlooError


def row(entity_id, name="Place", city="Denver", affinity=0.5):
    return {"entity_id": entity_id, "name": name, "types": ["urn:entity:place"],
            "properties": {"geocode": {"city": city}}, "query": {"affinity": affinity}}


def test_wrong_city_fuzzy_and_ambiguous_search_matches_are_unverified(monkeypatch):
    client = QlooClient("placeholder")
    for rows in ([row("a", city="Austin")], [row("a", name="Place Annex")],
                 [row("a"), row("b")]):
        monkeypatch.setattr(client, "_get", lambda *args: {"results": rows})
        assert client.resolve_place("Place", "Denver, Colorado") is None
    monkeypatch.setattr(client, "_get", lambda *args: {"results": [row("a")]})
    assert client.resolve_place("Place", "Denver, Colorado").entity_id == "a"


def test_urn_types_are_read_from_documented_types_field():
    assert QlooClient()._entity(row("a")).entity_type == "urn:entity:place"


def test_insights_generic_type_uses_specific_subtype():
    item = {"entity_id": "example", "name": "Example Place", "type": "urn:entity",
            "subtype": "urn:entity:place", "query": {"affinity": 0.73}}
    parsed = QlooClient()._scored(item)
    assert parsed.entity_type == "urn:entity:place"
    assert parsed.affinity == pytest.approx(0.73)


def test_city_only_popularity_is_not_misrepresented_as_affinity():
    item = row("example", affinity=None)
    item["popularity"] = 0.99
    item["query"] = {"quality": 0.95, "measurements": {"audience_growth": 0.2}}
    assert QlooClient()._scored(item).affinity is None


def test_accent_normalization_does_not_split_artist_or_city_names():
    assert qloo.normalize_name("Björk") == qloo.normalize_name("Bjork")
    assert qloo.normalize_name("Beyoncé") == qloo.normalize_name("Beyonce")
    assert qloo.normalize_name("São Paulo") == qloo.normalize_name("Sao Paulo")


@pytest.mark.parametrize("value", ["NaN", "Infinity", -0.1, 1.1, True, {"bad": "type"}])
def test_invalid_affinities_remain_missing(value):
    assert QlooClient()._scored(row("a", affinity=value)).affinity is None


def test_scoring_paginates_one_unchanged_universe(monkeypatch):
    client = QlooClient("placeholder")
    calls = []
    ids = [f"place-{index}" for index in range(70)]
    def get(path, params):
        calls.append(params)
        offset = (int(params["page"]) - 1) * 50
        return {"results": {"entities": [row(item) for item in ids[offset:offset + 50]]}}
    monkeypatch.setattr(client, "_get", get)
    scores = client.score_places(["anchor"], ids, "Denver")
    assert len(scores) == 70
    assert [call["page"] for call in calls] == ["1", "2"]
    assert len({call["filter.results.entities"] for call in calls}) == 1
    assert all(call["take"] == "50" for call in calls)


def test_repeated_page_does_not_create_fake_full_coverage(monkeypatch):
    client = QlooClient("placeholder")
    ids = [f"place-{index}" for index in range(70)]
    monkeypatch.setattr(client, "_get", lambda *args: {"results": {"entities": [row(item) for item in ids[:50]]}})
    with pytest.raises(QlooError, match="repeated"):
        client.score_places(["anchor"], ids, "Denver")


def test_reference_discovery_is_not_used_as_the_affinity_baseline(monkeypatch):
    client = QlooClient("placeholder")
    calls = []
    def get(path, params):
        calls.append(params)
        return {"results": {"entities": [row("a")]}}
    monkeypatch.setattr(client, "_get", get)
    client.city_reference_places("Denver")
    client.score_city_baseline(["a"], "Denver")
    assert calls[0]["sort_by"] == "affinity"
    assert "signal.interests.entities" not in calls[0]
    assert calls[1]["sort_by"] == "affinity"
    assert "signal.interests.entities" not in calls[1]


def test_provider_error_body_cannot_leak_into_public_error(monkeypatch):
    client = QlooClient("placeholder")
    def denied(*args, **kwargs):
        raise HTTPError("https://example.invalid", 401, "Unauthorized", {}, BytesIO(b"secret=do-not-expose"))
    monkeypatch.setattr(qloo, "urlopen", denied)
    monkeypatch.setattr(qloo.time, "sleep", lambda _: None)
    with pytest.raises(QlooError) as error:
        client._get("/search", {"query": "Place"})
    assert "401" in str(error.value)
    assert "do-not-expose" not in str(error.value)


def test_not_found_search_is_an_empty_match_not_provider_failure(monkeypatch):
    def missing(*args, **kwargs):
        raise HTTPError("https://example.invalid", 404, "Not found", {}, BytesIO())
    monkeypatch.setattr(qloo, "urlopen", missing)
    monkeypatch.setattr(qloo.time, "sleep", lambda _: None)
    assert QlooClient("placeholder")._get("/search", {"query": "Missing"}) == {"results": []}


def test_rate_limit_is_retried_with_a_bound(monkeypatch):
    attempts = []
    def rate_limit(*args, **kwargs):
        attempts.append(1)
        raise HTTPError("https://example.invalid", 429, "Too many", {}, BytesIO())
    monkeypatch.setattr(qloo, "urlopen", rate_limit)
    monkeypatch.setattr(qloo.time, "sleep", lambda _: None)
    with pytest.raises(QlooError, match="429"):
        QlooClient("placeholder")._get("/search", {"query": "Place"})
    assert len(attempts) == 3


def test_key_bearing_requests_cannot_follow_redirects():
    with pytest.raises(QlooError, match="redirect"):
        qloo.NoRedirect().redirect_request(None, None, 302, "Found", {}, "https://other.invalid")


def test_malformed_location_metadata_is_unverified(monkeypatch):
    client = QlooClient("placeholder")
    item = row("a")
    item["properties"] = "invalid"
    monkeypatch.setattr(client, "_get", lambda *args: {"results": [item]})
    assert client.resolve_place("Place", "Denver") is None
