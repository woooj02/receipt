"""Capture real-model outputs with repeat controls; requires explicit call permission."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent import AgentError, OpenAIAgent
from app.guard import CapacityError
from app.main import BatchTestRequest, CapturedProfile
from app.runtime import WorkTimeout, work_budget
from scripts.live_probe import write_private


def capture(spec, repeat, model):
    if not isinstance(spec, dict):
        raise ValueError("Study input must be a JSON object.")
    profiles = spec.get("profiles", [])
    if not isinstance(profiles, list):
        raise ValueError("Profiles must be a JSON array.")
    if not 2 <= len(profiles) * repeat <= 20:
        raise ValueError("Use 2–20 total captures, including repeats.")
    validated = [CapturedProfile.model_validate({**profile, "recommendations": ["validation-placeholder"]})
                 for profile in profiles]
    if len({profile.profile_id.casefold() for profile in validated}) != len(validated):
        raise ValueError("Profile IDs must be unique.")
    # Validate city and constraints before the first billable generation.
    prototype = [{**p.model_dump(), "profile_id": p.profile_id + "-run-" + str(index + 1),
                  "control_group": p.profile_id} for p in validated for index in range(repeat)]
    BatchTestRequest.model_validate({"agent_name": "validation", "agent_version": "validation",
        "prompt_version": "validation", "captured_at": datetime.now(timezone.utc).isoformat(),
        "city": spec.get("city", ""), "profiles": prototype,
        "constraints": spec.get("constraints", {"category": "restaurant"})})
    captured = []
    with work_budget(600):
        for profile in validated:
            for index in range(repeat):
                brief = {"anchors": profile.anchors, "city": spec["city"],
                         "goal": spec.get("goal", "Suggest three places for pre-show dinner."),
                         "constraints": spec.get("constraints", {"category": "restaurant"})}
                result = model.propose(brief)
                captured.append({"profile_id": profile.profile_id + "-run-" + str(index + 1),
                                 "control_group": profile.profile_id, "anchors": profile.anchors,
                                 "recommendations": result.recommendations})
    payload = {"agent_name": "OpenAI Responses capture", "agent_version": model.model,
               "prompt_version": "receipt-capture-v1-" + hashlib.sha256(json.dumps(
                   {"goal": spec.get("goal", "Suggest three places for pre-show dinner."),
                    "constraints": spec.get("constraints", {"category": "restaurant"})}, sort_keys=True).encode()).hexdigest()[:12],
               "captured_at": datetime.now(timezone.utc).isoformat(), "city": spec["city"],
               "profiles": captured, "demo": False, "constraints": spec.get("constraints", {"category": "restaurant"})}
    # A partial capture never becomes a completed study dataset.
    return BatchTestRequest.model_validate(payload).model_dump(mode="json")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="examples/study-input.json")
    parser.add_argument("--repeat", type=int, default=2, choices=(1, 2, 3))
    args = parser.parse_args()
    try:
        spec = json.loads(Path(args.input).read_text())
        report = capture(spec, args.repeat, OpenAIAgent())
    except (AgentError, CapacityError, WorkTimeout, ValueError, OSError, KeyError) as exc:
        print("Study was not completed: " + str(exc), file=sys.stderr)
        return 2
    print("Private captured-output dataset: " + str(write_private(report, "agent-captures")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
