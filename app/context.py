"""One frozen comparison set shared by profiles, revisions, and the baseline."""

from dataclasses import dataclass
import hashlib
import json

from .evaluation import complete_percentiles, fixed_universe
from .fixtures import DemoClient
from .qloo import Entity, QlooClient, normalize_name
from .runtime import progress
from .scope import Scope, assess


@dataclass
class Comparison:
    city: str
    client: QlooClient | DemoClient
    universe: list[Entity]
    resolutions: dict[str, Entity | None]
    baseline: dict[str, float | None]
    baseline_reason: str
    fingerprint: str
    scope: Scope

    @property
    def ids(self):
        return [entity.entity_id for entity in self.universe]

    @property
    def mode(self):
        return "DEMO" if isinstance(self.client, DemoClient) else "LIVE"

    def resolve(self, name):
        key = normalize_name(name)
        if key not in self.resolutions:
            # A new revision pick is resolved but cannot change the frozen set.
            self.resolutions[key] = self.client.resolve_place(name, self.city)
        return self.resolutions[key]

    def eligibility(self, entity):
        return assess(entity, self.scope, getattr(self.client, "restaurant_tag", None))


def prepare(city, candidates, force_demo=False, scope=None):
    scope = scope or Scope()
    progress("Resolving places and preparing one comparison set")
    live = QlooClient()
    client = DemoClient() if force_demo or not live.configured else live
    if scope.category != "any" or scope.venue:
        client.configure_scope(scope)
    resolutions = {normalize_name(name): client.resolve_place(name, city) for name in dict.fromkeys(candidates)}
    references = client.city_reference_places(city)
    eligible = lambda entity: assess(entity, scope, getattr(client, "restaurant_tag", None))[0] == "eligible"
    universe = fixed_universe([entity for entity in resolutions.values() if entity and eligible(entity)],
                              [entity for entity in references if eligible(entity)],
                              lambda entity: entity.entity_id)
    ids = [entity.entity_id for entity in universe]
    baseline = dict.fromkeys(ids)
    reason = "City-only affinity baseline has not passed live verification; Taste Lift is unavailable."
    if client.baseline_verified and ids:
        from .qloo import QlooError
        try:
            scores = score_map(client.score_city_baseline(ids, city), ids)
            baseline = complete_percentiles(scores)
            reason = "Complete baseline over the identical comparison set." if any(value is not None for value in baseline.values()) else "Baseline is incomplete or the universe is too small; Taste Lift is unavailable."
        except QlooError:
            reason = "City baseline request failed; Taste Lift is unavailable."
    fingerprint = hashlib.sha256(json.dumps({"city": normalize_name(city), "ids": ids, "constraints": scope.public()}, sort_keys=True).encode()).hexdigest()
    return Comparison(city, client, universe, resolutions, baseline, reason, fingerprint, scope)


def score_map(rows, ids):
    from .qloo import QlooError
    scores = dict.fromkeys(ids)
    seen = set()
    for entity in rows:
        if entity.entity_id not in scores or entity.entity_id in seen:
            raise QlooError("Unexpected or duplicated place in comparison scores.")
        seen.add(entity.entity_id)
        scores[entity.entity_id] = entity.affinity
    return scores
