"""A declared, equally weighted taste panel. It is not a population baseline."""

from .evaluation import complete_percentiles
from .qloo import QlooError
from .runtime import progress

VERSION = "contrasting-music-v3-pinned"
# Freeze inputs before inspecting target-profile results. These are curated
# contrasts, not sampled people, observed popularity or a representative crowd.
PROFILES = (
    ("pop", ("Taylor Swift", "Beyoncé")),
    ("metal", ("Metallica", "Iron Maiden")),
    ("latin", ("J Balvin", "Shakira")),
)
# Curated input identifiers, verified against Search before pinning. Runtime
# availability still requires complete affinity coverage; never drop a profile.
PINNED_IDS = {
    "pop": ("4BBEF799-A0C4-4110-AB01-39216993C312", "F6754C46-B3E7-457F-8B7E-06C613597320"),
    "metal": ("C445C761-CB38-4FEE-B085-D35F444A04DF", "BD2CDC36-5306-4213-A817-E7677E029CA6"),
    "latin": ("681CC85A-EBAD-40AB-A854-E4A9D6B4686B", "58F3AF6B-EC34-4BFC-B345-F4210EDE4C43"),
}


def build_panel(client, ids, city):
    missing = dict.fromkeys(ids)
    meta = {"version": VERSION, "available": False, "profiles": [],
            "synthetic": bool(getattr(client, "synthetic_evidence", False)),
            "definition": "Personal percentile minus the mean percentile of three fixed, equally weighted music profiles on identical place IDs and filters. Not a crowd or popularity estimate.",
            "reason": "Reference panel is not enabled for this source."}
    if meta["synthetic"]:
        meta["definition"] = "SYNTHETIC demonstration: invented personal and three invented panel score vectors; no live Qloo evidence. " + meta["definition"]
    if not getattr(client, "reference_panel_enabled", False) or not ids:
        return missing, meta
    ranks = []
    from .context import score_map
    try:
        for label, names in PROFILES:
            progress("Scoring declared reference panel: " + label)
            anchor_ids = PINNED_IDS[label]
            meta["profiles"].append({"label": label, "anchors": list(names),
                                     "entity_ids": list(anchor_ids), "weight": 1 / len(PROFILES)})
            scores = score_map(client.score_places(sorted(anchor_ids), ids, city), ids)
            ranked = complete_percentiles(scores)
            if not ranked or any(value is None for value in ranked.values()):
                raise QlooError("The panel requires complete scores for every reference profile.")
            ranks.append(ranked)
    except QlooError:
        meta["reason"] = "At least one declared profile is unresolved, incomplete or unavailable; no partial-panel metric is published."
        return missing, meta
    meta.update(available=True, reason="All three reference profiles scored the identical complete comparison set.")
    return {entity_id: sum(rank[entity_id] for rank in ranks) / len(ranks) for entity_id in ids}, meta


def for_person(metadata, anchors):
    """Return per-person overlap information without mutating a shared batch."""
    from .qloo import normalize_name
    ids = {anchor.entity_id for anchor in anchors if anchor}
    names = {normalize_name(anchor.name) for anchor in anchors if anchor}
    overlap = sorted({name for profile in metadata.get("profiles", [])
                      for name, entity_id in zip(profile["anchors"], profile["entity_ids"])
                      if entity_id in ids or normalize_name(name) in names})
    return {**metadata, "overlapping_anchors": overlap,
            "overlap_notice": ("Your tastes include " + ", ".join(overlap) +
                ", which also appears in the fixed comparison panel. Shared tastes can reduce the measured lift; the panel stays unchanged. Choose Taste match to check fit alone.") if overlap else None}
