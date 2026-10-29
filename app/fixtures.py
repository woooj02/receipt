"""Explicit synthetic catalog for offline workflow tests; never provider data."""

import hashlib

from .qloo import Entity, ScoredEntity, normalize_name
from .scope import Scope


DEMO_NAMES = ["Harbor Street Grill", "Copper Kettle", "Nightjar Lounge", "Juniper House", "Cobalt Noodles"]


class DemoClient:
    configured = False
    baseline_verified = True  # Synthetic baseline, explicitly marked as such.
    reference_panel_enabled = True
    synthetic_evidence = True

    def __init__(self):
        self.scope = Scope()
        self.restaurant_tag = "urn:tag:category:place:demo_restaurant"
        names = DEMO_NAMES + [f"Synthetic Reference {index:02d}" for index in range(1, 46)]
        self.catalog = {normalize_name(name): Entity(f"demo-{index}", name, "urn:entity:place",
                        latitude=39.74 + (index % 6 - 2) * 0.002,
                        longitude=-104.99 + (index % 7 - 3) * 0.002, tags=(self.restaurant_tag,))
                        for index, name in enumerate(names)}

    def configure_scope(self, scope):
        self.scope = scope

    def resolve_anchor(self, name, selected_id=None):
        entity = Entity(f"demo-anchor-{normalize_name(name)}", name, "demo:anchor")
        return entity if selected_id is None or entity.entity_id == selected_id else None

    def resolve_place(self, name, city):
        return self.catalog.get(normalize_name(name))

    def city_reference_places(self, city):
        return list(self.catalog.values())

    def score_places(self, anchor_ids, candidate_ids, city):
        from .reference_panel import PINNED_IDS
        if set(anchor_ids) in [set(ids) for ids in PINNED_IDS.values()]:
            # Explicitly invented panel scores, not cached Qloo evidence.
            return self._scores(candidate_ids, sorted(anchor_ids), panel=True)
        return self._scores(candidate_ids, sorted(anchor_ids))

    def score_city_baseline(self, candidate_ids, city):
        return self._scores(candidate_ids, None)

    def _scores(self, candidate_ids, anchors, panel=False):
        scored = []
        for entity in self.catalog.values():
            if entity.entity_id not in candidate_ids:
                continue
            index = int(entity.entity_id.removeprefix("demo-"))
            if index < 5:
                value = (0.94, 0.10, 0.90, 0.98, 0.96)[index] if anchors and not panel else (0.30, 0.10, 0.98, 0.40, 0.35)[index]
            else:
                value = 0.20 + (index - 5) / 44 * 0.68
            if anchors:
                seed = "|".join(anchors + [entity.entity_id])
                perturbation = int(hashlib.sha256(seed.encode()).hexdigest()[:4], 16) / 65535 - 0.5
                value += perturbation * (0.08 if panel and index >= 5 else 0.012)
            scored.append(ScoredEntity(entity.entity_id, entity.name, entity.entity_type, value))
        return scored
