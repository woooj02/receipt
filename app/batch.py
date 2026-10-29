"""Evaluate captured agent outputs over one shared comparison set."""

from __future__ import annotations

import secrets

from .context import prepare
from .evaluation import CapturedAgentRun, sensitivity
from .qloo import normalize_name
from .receipt import AuditError, audit


def run_test_suite(*, agent, city, profiles, force_demo, policy="standard", scope=None):
    if len({profile["profile_id"] for profile in profiles}) != len(profiles):
        raise AuditError("Use unique profile IDs.")
    # Resolve the union once. No profile gets a friendlier comparison set simply
    # because its agent selected different places.
    all_names = list(dict.fromkeys(name for profile in profiles for name in profile["recommendations"]))
    comparison = prepare(city, all_names, force_demo, scope)
    audits, captured, candidates = [], [], []
    suite_id = f"suite_{secrets.token_hex(12)}"
    for profile in profiles:
        from .runtime import progress
        progress(f"Evaluating captured profile {len(audits) + 1} of {len(profiles)}")
        result = audit(anchors=profile["anchors"], candidates=profile["recommendations"],
                       city=city, force_demo=force_demo, policy=policy, comparison=comparison,
                       owner=suite_id, scope=scope)
        audits.append({"profile_id": profile["profile_id"], "audit_id": result["audit_id"],
                       "source": result["source"], "candidates": result["candidates"],
                       "scoring_coverage": result["scoring_coverage"],
                       "comparison_fingerprint": result["comparison_fingerprint"]})
        captured.append(CapturedAgentRun(profile["profile_id"],
                        frozenset(normalize_name(name) for name in profile["recommendations"])))
        candidates.extend(result["candidates"])

    total = len(candidates)
    baseline_eligible = sum(row["taste_lift"] is not None for row in candidates)
    generic = sum(row["status"] == "generic" for row in candidates)
    has_baseline = any(value is not None for value in comparison.baseline.values())
    controls = {}
    for profile, capture in zip(profiles, captured):
        if profile.get("control_group"):
            key = profile["control_group"]
            identity = frozenset(map(normalize_name, profile["anchors"]))
            if key in controls and controls[key]["anchors"] != identity:
                raise AuditError("Repeat controls must use the same tastes within each control group.")
            controls.setdefault(key, {"anchors": identity, "runs": []})["runs"].append(capture)
    repeat_variation = [sensitivity(group["runs"]) for group in controls.values() if len(group["runs"]) >= 2]
    return {
        "suite_id": suite_id, "agent": agent, "city": city,
        "source": audits[0]["source"], "profile_count": len(profiles), "policy": policy,
        "fixed_universe_count": len(comparison.ids), "comparison_fingerprint": comparison.fingerprint,
        "constraints": comparison.scope.public(),
        "unique_taste_profile_count": len({tuple(sorted(map(normalize_name, profile["anchors"]))) for profile in profiles}),
        "metrics": {
            "sensitivity": sensitivity(captured),
            "sensitivity_definition": "Mean pairwise Jaccard distance of normalized supplied place names. Measures output variation, not quality.",
            "generic_rate": generic / total if total and has_baseline else None,
            "generic_rate_available": has_baseline,
            "generic_count": generic if has_baseline else None,
            "generic_definition": "Share of all submitted picks that clear the personalized-fit bar but fail the policy's rank-lift bar. Missing evidence is counted separately.",
            "baseline_eligible_count": baseline_eligible,
            "mismatch_rate": sum(row["status"] == "mismatch" for row in candidates) / total,
            "unverified_rate": sum(row["status"] == "unverified" for row in candidates) / total,
            "recommendation_count": total,
            "constraint_failure_rate": sum(row["status"] == "ineligible" for row in candidates) / total,
            "repeat_control_variation": sum(repeat_variation) / len(repeat_variation) if repeat_variation else None,
            "repeat_control_groups": len(repeat_variation),
        },
        "profiles": audits,
        "limitations": [
            "Receipt does not verify the claimed agent, prompt, or capture provenance.",
            "Sensitivity measures output variation. Repeated runs of the same profile are needed to separate taste sensitivity from model randomness.",
            "Qloo-relative rates retain every submitted pick in the denominator; missing and ambiguous picks are unverified.",
            "Generic rate requires a verified complete city baseline. Coverage is reported separately.",
            "All profiles share the same frozen set. Different recommendation sets alone do not prove better personalization.",
        ],
    }
