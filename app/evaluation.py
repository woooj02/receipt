"""Deterministic evaluation rules behind Receipt's cultural QA claims.

These functions deliberately operate on a fixed universe and its rank percentiles,
not provider scores from different queries. That makes a comparison explainable and
prevents the best item in a tiny, bad recommendation list from looking excellent.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import isfinite
from typing import Callable, Iterable, TypeVar


T = TypeVar("T")


@dataclass(frozen=True)
class Policy:
    name: str
    minimum_personal_percentile: float
    minimum_taste_lift: float
    require_city_baseline: bool


POLICIES = {
    "standard": Policy("Standard", 0.60, 0.10, False),
    "verified_only": Policy("Verified-only", 0.70, 0.15, True),
}
MIN_UNIVERSE_SIZE = 10


@dataclass(frozen=True)
class Decision:
    status: str
    personal_percentile: float | None
    city_percentile: float | None
    taste_lift: float | None
    reason: str


def percentiles(scores: dict[str, float | None]) -> dict[str, float | None]:
    """Return descending mid-rank percentiles for one fixed candidate universe.

    The top of a distinct three-item universe is 1.0, the middle is 0.5, and the
    bottom is 0.0. Equal values share a mid-rank instead of receiving arbitrary
    order-dependent ranks. Missing values stay missing.
    """
    known = [(entity_id, score) for entity_id, score in scores.items()
             if isinstance(score, (int, float)) and not isinstance(score, bool) and isfinite(score)]
    output: dict[str, float | None] = {entity_id: None for entity_id in scores}
    if not known:
        return output
    if len(known) == 1:
        # One observation is no evidence of comparative rank.
        return output

    known.sort(key=lambda item: item[1], reverse=True)
    position = 0
    while position < len(known):
        end = position + 1
        while end < len(known) and known[end][1] == known[position][1]:
            end += 1
        mid_index = (position + end - 1) / 2
        percentile = (len(known) - 1 - mid_index) / (len(known) - 1)
        for entity_id, _ in known[position:end]:
            output[entity_id] = percentile
        position = end
    return output


def complete_percentiles(scores: dict[str, float | None]) -> dict[str, float | None]:
    """An incomplete or tiny universe cannot establish comparable fit ranks."""
    if len(scores) < MIN_UNIVERSE_SIZE or any(
        value is None or not isinstance(value, (int, float)) or isinstance(value, bool)
        or not isfinite(value) for value in scores.values()
    ):
        return dict.fromkeys(scores)
    return percentiles(scores)


def fixed_universe(
    agent_items: Iterable[T],
    reference_items: Iterable[T],
    identifier: Callable[[T], str],
    limit: int = 200,
) -> list[T]:
    """Keep every resolved agent item, then fill the remaining fixed universe.

    The caller supplies only resolved entities and an identifier function. A small
    agent list therefore cannot create a favourable ranking by excluding better
    city alternatives from the comparison set.
    """
    selected: list[T] = []
    seen: set[str] = set()
    for item in list(agent_items) + list(reference_items):
        item_id = identifier(item)
        if item_id in seen:
            continue
        selected.append(item)
        seen.add(item_id)
    if len(selected) > limit:
        raise ValueError("The comparison universe is too large; no agent picks were silently dropped.")
    return sorted(selected, key=identifier)


def decide(
    *,
    personal_percentile: float | None,
    city_percentile: float | None,
    policy: Policy,
) -> Decision:
    """Classify one proposed place without turning missing evidence into zero."""
    if personal_percentile is None:
        return Decision("unverified", None, city_percentile, None, "Receipt could not score this exact place in the fixed universe.")
    if policy.require_city_baseline and city_percentile is None:
        return Decision("unverified", personal_percentile, None, None, "Verified-only requires a valid city baseline for this place.")
    taste_lift = None if city_percentile is None else personal_percentile - city_percentile
    if personal_percentile < policy.minimum_personal_percentile:
        return Decision("mismatch", personal_percentile, city_percentile, taste_lift, "Its personalized rank is below this policy’s cultural-fit bar.")
    if city_percentile is None:
        return Decision("supported", personal_percentile, None, None, "It clears the personalized cultural-fit bar; city baseline was unavailable.")

    assert taste_lift is not None
    if taste_lift < policy.minimum_taste_lift:
        return Decision("generic", personal_percentile, city_percentile, taste_lift, "It clears the fit bar but has insufficient measured rank lift. This alone does not establish that it is a bad recommendation.")
    return Decision("supported", personal_percentile, city_percentile, taste_lift, "It clears both personalized-fit and Taste Lift bars.")


@dataclass(frozen=True)
class CapturedAgentRun:
    """One agent output captured for a named test profile.

    The test suite does not generate this output or imply that it came from a real
    model. Its source, prompt version, and capture date are required at the API
    boundary before a run can be presented as evidence.
    """

    profile_id: str
    recommendations: frozenset[str]


def sensitivity(runs: Iterable[CapturedAgentRun]) -> float | None:
    """Mean pairwise Jaccard distance across captured agent outputs.

    0 means every tested profile received the same set; 1 means no pair shares a
    recommendation. It measures output variation, not recommendation quality.
    """
    captured = list(runs)
    if len(captured) < 2:
        return None
    distances: list[float] = []
    for left, right in combinations(captured, 2):
        union = left.recommendations | right.recommendations
        distances.append(0.0 if not union else 1 - len(left.recommendations & right.recommendations) / len(union))
    return sum(distances) / len(distances)


def rates(decisions: Iterable[Decision]) -> dict[str, float | int]:
    """Return transparent category rates for a batch of Receipt decisions."""
    items = list(decisions)
    total = len(items)
    if not total:
        return {"count": 0, "generic_rate": 0.0, "mismatch_rate": 0.0, "unverified_rate": 0.0}
    return {
        "count": total,
        "generic_rate": sum(item.status == "generic" for item in items) / total,
        "mismatch_rate": sum(item.status == "mismatch" for item in items) / total,
        "unverified_rate": sum(item.status == "unverified" for item in items) / total,
    }
