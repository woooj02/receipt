import math

import pytest

from app.evaluation import POLICIES, CapturedAgentRun, complete_percentiles, decide, fixed_universe, percentiles, sensitivity


def test_rank_ties_and_missing_values():
    assert percentiles({"a": 0.9, "b": 0.9, "c": 0.7}) == {"a": 0.75, "b": 0.75, "c": 0.0}
    assert percentiles({"a": 0.9, "b": None}) == {"a": None, "b": None}


@pytest.mark.parametrize("bad", [None, math.nan, math.inf, -math.inf, True])
def test_incomplete_or_invalid_universe_has_no_comparable_ranks(bad):
    scores = {str(index): index / 50 for index in range(50)}
    scores["0"] = bad
    assert all(value is None for value in complete_percentiles(scores).values())


def test_fixed_universe_never_truncates_agent_picks():
    agents = [f"agent-{index}" for index in range(120)]
    references = [f"reference-{index}" for index in range(50)]
    result = fixed_universe(agents, references, lambda name: name)
    assert len(result) == 170
    assert set(agents) <= set(result)
    assert result == fixed_universe(reversed(agents), reversed(references), lambda name: name)


def test_mismatch_retains_lift_instead_of_deleting_measurement():
    result = decide(personal_percentile=0.4, city_percentile=0.2, policy=POLICIES["standard"])
    assert result.status == "mismatch"
    assert result.taste_lift == pytest.approx(0.2)


def test_sensitivity_does_not_call_variation_quality():
    identical = [CapturedAgentRun(str(i), frozenset({"a", "b"})) for i in range(3)]
    disjoint = [CapturedAgentRun(str(i), frozenset({str(i)})) for i in range(3)]
    assert sensitivity(identical) == 0
    assert sensitivity(disjoint) == 1
    assert sensitivity(identical[:1]) is None
