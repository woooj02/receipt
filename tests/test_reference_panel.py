import math

import pytest

from app.evaluation import POLICIES, decide
from app.qloo import Entity, QlooClient, ScoredEntity
from app.reference_panel import PROFILES, PINNED_IDS, build_panel, for_person
from app.qloo import QlooError


class PanelGraph:
    reference_panel_enabled = True

    def __init__(self, incomplete=False, unresolved=False):
        self.calls = []
        self.incomplete, self.unresolved = incomplete, unresolved

    def resolve_anchor(self, name):
        raise AssertionError("Pinned panel must not search by name at runtime")

    def score_places(self, anchors, ids, city):
        self.calls.append((tuple(ids), city, tuple(anchors)))
        if self.unresolved:
            raise QlooError("Pinned profile unavailable")
        # First and third profiles rank ascending, second descending.
        reverse = PINNED_IDS["metal"][0] in anchors
        return [ScoredEntity(i, i, "urn:entity:place", None if self.incomplete and len(self.calls) == 2 and n == 0
                             else (len(ids) - n if reverse else n) / len(ids)) for n, i in enumerate(ids)]


def test_panel_is_mean_of_complete_percentiles_on_identical_ids_and_city():
    ids = [str(i) for i in range(12)]
    client = PanelGraph()
    ranks, metadata = build_panel(client, ids, "Denver")
    assert metadata["available"] and len(metadata["profiles"]) == 3
    assert all(call[:2] == (tuple(ids), "Denver") for call in client.calls)
    assert ranks["0"] == pytest.approx(1 / 3)
    assert ranks["11"] == pytest.approx(2 / 3)
    assert sum(p["weight"] for p in metadata["profiles"]) == pytest.approx(1)
    assert "Not a crowd" in metadata["definition"]


@pytest.mark.parametrize("kwargs", [{"incomplete": True}, {"unresolved": True}])
def test_panel_never_drops_a_failed_profile_to_manufacture_a_baseline(kwargs):
    ranks, metadata = build_panel(PanelGraph(**kwargs), [str(i) for i in range(12)], "Denver")
    assert not metadata["available"] and all(v is None for v in ranks.values())


def test_overlap_is_per_person_and_does_not_change_the_shared_panel():
    _, metadata = build_panel(PanelGraph(), [str(i) for i in range(12)], "Denver")
    personal = for_person(metadata, [Entity(PINNED_IDS['pop'][0], 'Taylor Swift', 'urn:entity:artist')])
    assert personal['overlapping_anchors'] == ['Taylor Swift']
    assert personal['overlap_notice'] and 'overlapping_anchors' not in metadata
    assert personal['profiles'] == metadata['profiles']
    assert not for_person(metadata, [Entity('other', 'Other', 'urn:entity:artist')])['overlap_notice']


def test_synthetic_distinctive_policy_has_a_complete_clearly_synthetic_panel():
    from app.receipt import audit
    result = audit(anchors=['Kendrick Lamar', 'The Bear'],
                   candidates=['Harbor Street Grill', 'Copper Kettle', 'Nightjar Lounge'],
                   city='Denver', force_demo=True, policy='personalized')
    assert result['source']['mode'] == 'DEMO'
    assert result['reference_panel']['available']
    assert {row['status'] for row in result['candidates']} == {'supported', 'mismatch', 'shared_taste'}


@pytest.mark.parametrize("personal,panel,status", [(.9, .5, "supported"), (.7, .6, "supported"), (.7, .65, "shared_taste"),
                                                  (.3, .2, "mismatch"), (.9, None, "unverified")])
def test_distinctive_policy_uses_a_named_panel_without_fabricating_city_lift(personal, panel, status):
    result = decide(personal_percentile=personal, city_percentile=None,
                    panel_percentile=panel, policy=POLICIES["personalized"])
    assert result.status == status and result.taste_lift is None and result.city_percentile is None


def test_provider_metadata_and_contributions_are_validated_without_changing_affinity():
    row = QlooClient("placeholder")._scored({"entity_id": "place", "name": "Place", "type": "urn:entity:place",
        "properties": {"image": {"url": "https://images.qloo.com/i/example.jpg"}, "address": "Street, Denver",
                       "business_rating": 4.5, "price_level": 2},
        "query": {"affinity": .8, "explainability": {"signal.interests.entities": [
            {"entity_id": "artist", "score": .6}, {"entity_id": "film", "score": .4},
            {"entity_id": "bad", "score": True}, {"entity_id": "nan", "score": math.nan}]}}})
    assert row.affinity == .8 and row.business_rating == 4.5 and row.address == "Street, Denver"
    assert row.contributions == (("artist", .6), ("film", .4))
    assert row.image_url == "https://images.qloo.com/i/example.jpg"


@pytest.mark.parametrize("url", ["http://images.qloo.com/a", "https://evil.test/a", "https://images.qloo.com.evil.test/a",
                                  "https://user:pass@images.qloo.com/a", "https://images.qloo.com:444/a"])
def test_untrusted_images_never_reach_the_browser(url):
    row = QlooClient("placeholder")._scored({"entity_id": "p", "name": "P", "properties": {"image": {"url": url}}})
    assert row.image_url is None


@pytest.mark.parametrize("personal,status,low_rate", [(.7, "supported", 0),
    (.7 - 1e-9, "shared_taste", 1), (.7 + 1e-9, "supported", 0)])
def test_batch_and_policy_agree_at_panel_threshold(monkeypatch, personal, status, low_rate):
    from types import SimpleNamespace
    from app import batch
    from app.scope import Scope

    panel = .6  # Observed live boundary: .7 - .6 is 0.09999999999999998.
    decision = decide(personal_percentile=personal, city_percentile=None,
                      panel_percentile=panel, policy=POLICIES["personalized"])
    assert decision.status == status
    comparison = SimpleNamespace(baseline={"p": None}, panel_metadata={"available": True},
                                 ids=["p"], fingerprint="fixed", scope=Scope())
    monkeypatch.setattr(batch, "prepare", lambda *args: comparison)
    monkeypatch.setattr(batch, "audit", lambda **kwargs: {
        "audit_id": "audit-example", "source": {"mode": "DEMO"},
        "reference_panel": comparison.panel_metadata,
        "scoring_coverage": {"complete": True}, "comparison_fingerprint": "fixed",
        "candidates": [{"status": decision.status, "personal_percentile": personal,
                        "panel_lift": personal - panel, "taste_lift": None}],
    })
    result = batch.run_test_suite(agent={"name": "Boundary fixture"}, city="Denver", force_demo=True,
        policy="personalized", profiles=[{"profile_id": name, "anchors": ["A", "B"], "recommendations": ["P"]}
                                         for name in ["first", "second"]])
    assert result["metrics"]["low_panel_lift_rate"] == low_rate
