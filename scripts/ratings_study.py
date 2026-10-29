"""Run the actual taste-blind ratings agent locally. Not an LLM benchmark.

Uses QLOO_API_KEY from the environment; never calls the hosted app or loads model
credentials. Inputs are fixed before scoring. Provider evidence stays private.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.agent import QlooDiscoveryAgent
from app.batch import run_test_suite
from app.main import BatchTestRequest
from app.runtime import work_budget
from scripts.live_probe import write_private


def run(spec):
    captured_at = datetime.now(timezone.utc).isoformat()
    prototype = {"agent_name": "Generic ratings rules agent (not an LLM)",
        "agent_version": QlooDiscoveryAgent.model, "prompt_version": "ratings-study-v1",
        "captured_at": captured_at, "city": spec["city"], "constraints": spec["constraints"],
        "profiles": [{**p, "recommendations": ["validation-placeholder"]} for p in spec["profiles"]],
        "policy": "personalized", "demo": False}
    request = BatchTestRequest.model_validate(prototype)
    model = QlooDiscoveryAgent()
    captures = []
    # Discovery is actually executed for each profile; cache reuse is allowed.
    # The rules intentionally ignore tastes, so zero sensitivity is expected.
    with work_budget(600):
        for profile in request.profiles:
            proposal = model.propose({"anchors": profile.anchors, "city": request.city,
                                      "constraints": request.constraints.model_dump()})
            captures.append({**profile.model_dump(), "recommendations": proposal.recommendations})
        dataset = {**prototype, "profiles": captures}
        payload = BatchTestRequest.model_validate(dataset)
        report = run_test_suite(agent={"name": payload.agent_name, "version": payload.agent_version,
            "prompt_version": payload.prompt_version, "captured_at": captured_at,
            "provenance": "local_rules_agent_executed_by_study_script"}, city=payload.city,
            profiles=[p.model_dump() for p in payload.profiles], force_demo=False,
            policy=payload.policy, scope=payload.constraints.to_scope())
    counts = Counter(row["status"] for profile in report["profiles"] for row in profile["candidates"])
    total = sum(counts.values())
    summary = {"captured_at": captured_at, "source": "live Qloo; actual rules agent, no LLM",
        "input_sha256": hashlib.sha256(json.dumps(spec, sort_keys=True).encode()).hexdigest(),
        "profiles": len(captures), "recommendations": total, "status_counts": dict(counts),
        "failed_distinctive_policy": total - counts["supported"],
        "complete_profiles": sum(p["scoring_coverage"]["complete"] for p in report["profiles"]),
        "panel_version": report["reference_panel"]["version"],
        "metrics": report["metrics"],
        "limits": "Ten curated profiles, one venue and one taste-blind rules agent. Repeated picks are not independent samples. These are declared evaluator decisions, not human enjoyment, population popularity or evidence of LLM blindness. Includes all input profiles and outcomes; no post-score selection."}
    return dataset, report, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", default="examples/ratings-study.json")
    args = parser.parse_args()
    spec = json.loads(Path(args.input).read_text())
    # Save the exact declared cohort before any scores are observed.
    print("Frozen input:", write_private(spec, "ratings-study-input"), flush=True)
    dataset, report, summary = run(spec)
    for data, name in ((dataset, "ratings-study-captures"), (report, "ratings-study-report"), (summary, "ratings-study-summary")):
        print(name + ":", write_private(data, name), flush=True)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
