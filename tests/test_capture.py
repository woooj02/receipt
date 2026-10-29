import pytest

from app.agent import Proposal
from scripts.capture_study import capture
from scripts.live_probe import collect
from app.qloo import QlooError
from app.scope import Scope


class CapturedModel:
    model = "contract-test-model"
    def __init__(self):
        self.calls = []

    def propose(self, brief):
        self.calls.append(brief)
        return Proposal(recommendations=["Example A", "Example B"], note="Contract test output")


def spec():
    return {"city": "Denver", "constraints": {"category": "restaurant"},
            "profiles": [{"profile_id": "rap", "anchors": ["Artist A", "Film A"]},
                         {"profile_id": "jazz", "anchors": ["Artist B", "Film B"]}]}


def test_capture_produces_importable_repeat_controls_with_constraints():
    model = CapturedModel()
    data = capture(spec(), 2, model)
    assert len(model.calls) == len(data["profiles"]) == 4
    assert data["profiles"][0]["control_group"] == data["profiles"][1]["control_group"]
    assert data["profiles"][0]["profile_id"] != data["profiles"][1]["profile_id"]
    assert data["demo"] is False
    assert all(call["constraints"]["category"] == "restaurant" for call in model.calls)


@pytest.mark.parametrize("change", [
    {"city": " "}, {"constraints": {"category": "unknown"}},
    {"profiles": [{"profile_id": "same", "anchors": ["A", "B"]},
                  {"profile_id": "SAME", "anchors": ["C", "D"]}]},
    {"profiles": "wrong type"},
])
def test_invalid_capture_inputs_are_rejected_before_any_generation(change):
    model = CapturedModel()
    data = {**spec(), **change}
    with pytest.raises(ValueError):
        capture(data, 2, model)
    assert model.calls == []


def test_capture_refuses_more_than_twenty_model_calls():
    model = CapturedModel()
    data = spec()
    data["profiles"] = [{"profile_id": str(i), "anchors": ["Artist", "Film"]} for i in range(11)]
    with pytest.raises(ValueError, match="total captures"):
        capture(data, 2, model)
    assert not model.calls


def test_missing_qloo_key_does_not_silently_run_a_synthetic_probe():
    with pytest.raises(QlooError, match="No requests"):
        collect(["Artist", "Film"], ["Place"], "Denver", Scope())
