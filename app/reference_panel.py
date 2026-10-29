"""A declared, equally weighted taste panel. It is not a population baseline."""

from .evaluation import complete_percentiles
from .qloo import QlooError
from .runtime import progress

VERSION = "contrasting-music-v2"
# Freeze inputs before inspecting target-profile results. These are curated
# contrasts, not sampled people, observed popularity or a representative crowd.
PROFILES = (
    ("pop", ("Taylor Swift", "Beyoncé")),
    ("metal", ("Metallica", "Iron Maiden")),
    ("latin", ("J Balvin", "Shakira")),
)


def build_panel(client, ids, city):
    missing = dict.fromkeys(ids)
    meta = {"version": VERSION, "available": False, "profiles": [],
            "definition": "Personal percentile minus the mean percentile of three fixed, equally weighted music profiles on identical place IDs and filters. Not a crowd or popularity estimate.",
            "reason": "Reference panel is not enabled for this source."}
    if not getattr(client, "reference_panel_enabled", False) or not ids:
        return missing, meta
    ranks = []
    from .context import score_map
    try:
        for label, names in PROFILES:
            progress("Scoring declared reference panel: " + label)
            anchors = [client.resolve_anchor(name) for name in names]
            if not all(anchors) or len({anchor.entity_id for anchor in anchors}) != len(names):
                raise QlooError("A panel anchor could not be uniquely resolved.")
            meta["profiles"].append({"label": label, "anchors": list(names),
                                     "entity_ids": [anchor.entity_id for anchor in anchors], "weight": 1 / len(PROFILES)})
            scores = score_map(client.score_places(sorted(anchor.entity_id for anchor in anchors), ids, city), ids)
            ranked = complete_percentiles(scores)
            if not ranked or any(value is None for value in ranked.values()):
                raise QlooError("The panel requires complete scores for every reference profile.")
            ranks.append(ranked)
    except QlooError:
        meta["reason"] = "At least one declared profile is unresolved, incomplete or unavailable; no partial-panel metric is published."
        return missing, meta
    meta.update(available=True, reason="All three reference profiles scored the identical complete comparison set.")
    return {entity_id: sum(rank[entity_id] for rank in ranks) / len(ranks) for entity_id in ids}, meta
