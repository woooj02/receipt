"""Receipt audits immutable score snapshots against a frozen comparison set."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import secrets
from threading import RLock
import time

from .context import Comparison, prepare, score_map
from .evaluation import POLICIES, complete_percentiles, decide
from .qloo import QlooError, normalize_name
from .runtime import progress, remaining
from .scope import Scope

PENDING: dict = {}
_LOCK = RLock()
APPROVAL_TTL_SECONDS = 30 * 60
MAX_PENDING = 1000


class AuditError(ValueError):
    """A request cannot produce or approve an honest audit."""


def audit(*, anchors, candidates, city, force_demo=False, revision_of=None,
          policy="standard", owner="local", comparison: Comparison | None = None, scope=None):
    scope = scope or Scope()
    _validate(anchors, candidates, city, policy)
    with _LOCK:
        _discard_expired()
        previous = PENDING.get(revision_of) if revision_of else None
        if revision_of and (not previous or previous["owner"] != owner):
            raise AuditError("Original audit is unavailable in this session.")
        if previous:
            original = previous["result"]
            if (normalize_name(city) != normalize_name(original["city"])
                    or sorted(map(normalize_name, anchors)) != sorted(map(normalize_name, original["input_anchors"]))
                    or policy != original["policy_id"]):
                raise AuditError("A revision must keep the same tastes, city, and policy. Start a new audit to change them.")
            if scope.public() != original["constraints"]:
                raise AuditError("A revision must keep the same restaurant and venue constraints.")
            if {normalize_name(name) for name in candidates} == {normalize_name(name) for name in original["input_candidates"]}:
                raise AuditError("Reordering the same places is not a revised recommendation set.")
            comparison = previous["comparison"]
            if force_demo != original["requested_demo"]:
                raise AuditError("A revision cannot change its evidence mode.")
    comparison = comparison or prepare(city, candidates, force_demo, scope)
    result = _evaluate(comparison, anchors, candidates, policy)
    remaining()
    result.update(input_anchors=list(anchors), input_candidates=list(candidates),
                  requested_demo=force_demo, re_audit_of=revision_of)
    result["approval_eligible"] = bool(result["candidates"]) and all(
        row["status"] == "supported" for row in result["candidates"])
    result["verdict"] = _verdict(result)
    # The hash covers the scored evidence, policy, provenance and universe.
    result["fingerprint"] = hashlib.sha256(
        json.dumps(result, sort_keys=True, ensure_ascii=True, allow_nan=False).encode()).hexdigest()
    result["audit_id"] = secrets.token_urlsafe(18)
    result["expires_at"] = int(time.time() + APPROVAL_TTL_SECONDS)
    with _LOCK:
        if previous:
            previous["superseded"] = True
        PENDING[result["audit_id"]] = {
            "result": deepcopy(result), "comparison": comparison, "owner": owner,
            "review_token": secrets.token_urlsafe(32), "issued": None, "superseded": False,
        }
        while len(PENDING) > MAX_PENDING:
            PENDING.pop(next(iter(PENDING)))
    return deepcopy(result)


def review(audit_id, owner):
    """Issue a confirmation token for this session's exact score snapshot."""
    with _LOCK:
        entry = _entry(audit_id, owner)
        if not entry["result"]["approval_eligible"] or entry["superseded"]:
            raise AuditError("This audit cannot be approved. Review the current passing result.")
        return {"audit_id": audit_id, "fingerprint": entry["result"]["fingerprint"],
                "review_token": entry["review_token"]}


def approve(audit_id, *, owner="local", review_token=None, fingerprint=None):
    """Record explicit browser confirmation, not an attestation of human identity."""
    with _LOCK:
        entry = _entry(audit_id, owner)
        result = entry["result"]
        if not result["approval_eligible"] or entry["superseded"]:
            raise AuditError("This audit is incomplete, failed, or superseded and cannot be approved.")
        if not review_token or not secrets.compare_digest(review_token, entry["review_token"]):
            raise AuditError("Explicit review confirmation is required.")
        if fingerprint != result["fingerprint"]:
            raise AuditError("The reviewed fingerprint does not match this score snapshot.")
        if not entry["issued"]:
            entry["issued"] = {
                "receipt_id": f"rcpt_{secrets.token_hex(12)}", "issued_at": int(time.time()),
                "approval_recorded": True, "approval_method": "browser_confirmation",
                "approval_identity_verified": False,
                "source": result["source"], "city": result["city"], "anchors": result["anchors"],
                "approved_recommendations": result["candidates"], "policy": result["policy"],
                "limitations": result["limitations"], "audit_fingerprint": result["fingerprint"],
                "comparison_fingerprint": result["comparison_fingerprint"],
                "re_audit_of": result["re_audit_of"],
                "constraints": result["constraints"],
            }
        return deepcopy(entry["issued"])


def _evaluate(context, anchors, candidates, policy_id):
    progress("Resolving cultural anchors")
    client = context.client
    resolved_anchors = [client.resolve_anchor(name) for name in anchors]
    distinct = {item.entity_id for item in resolved_anchors if item}
    anchor_complete = all(resolved_anchors) and len(distinct) == len(anchors)
    trace = [{"step": "Resolve tastes", "state": "complete" if anchor_complete else "partial",
              "detail": f"{len(distinct)} of {len(anchors)} distinct anchors resolved."},
             {"step": "Freeze comparison set", "state": "complete",
              "detail": f"{len(context.ids)} places; the same set is used for every profile and revision."}]
    progress("Scoring the frozen comparison set")
    scored = score_map(client.score_places(sorted(distinct), context.ids, context.city), context.ids) if anchor_complete and context.ids else dict.fromkeys(context.ids)
    personal = complete_percentiles(scored)
    ranks_available = any(value is not None for value in personal.values())
    trace.append({"step": "Score comparison set", "state": "complete" if ranks_available else "unavailable",
                  "detail": f"{sum(value is not None for value in scored.values())}/{len(context.ids)} scores. All comparison places must be scored before ranks are reported."})
    trace.append({"step": "City baseline", "state": "complete" if any(value is not None for value in context.baseline.values()) else "unavailable",
                  "detail": context.baseline_reason})
    selected_policy = POLICIES[policy_id]
    ablations = {}
    if ranks_available:
        for omitted in sorted(distinct):
            progress("Checking the effect of removing one taste")
            try:
                rows = client.score_places(sorted(distinct - {omitted}), context.ids, context.city)
                ablations[omitted] = complete_percentiles(score_map(rows, context.ids))
            except QlooError:
                ablations[omitted] = dict.fromkeys(context.ids)
        trace.append({"step": "Remove one taste at a time", "state": "complete" if all(
            any(value is not None for value in ranks.values()) for ranks in ablations.values()) else "partial",
            "detail": "Rank changes show score sensitivity to an omitted anchor; they do not establish causation."})
    anchor_names = {item.entity_id: item.name for item in resolved_anchors if item}
    output = []
    for name in candidates:
        entity = context.resolve(name)
        entity_id = entity.entity_id if entity else None
        eligibility, constraint_reason, measured_distance = context.eligibility(entity)
        decision = decide(personal_percentile=personal.get(entity_id),
                          city_percentile=context.baseline.get(entity_id), policy=selected_policy)
        row = {"name": name, "resolved_name": entity.name if entity else None, "entity_id": entity_id,
               **asdict(decision), "affinity": scored.get(entity_id), "anchor_removals": []}
        row.update(constraints_status=eligibility, distance_m=measured_distance)
        if eligibility != "eligible":
            row.update(status=eligibility, reason=constraint_reason, personal_percentile=None,
                       city_percentile=None, taste_lift=None)
        elif entity_id not in personal:
            row["reason"] = ("This place is outside the frozen comparison set. Start a new audit to test it."
                             if entity else "Qloo could not uniquely verify this name in the requested city.")
        elif not anchor_complete:
            row["reason"] = "The taste profile is incomplete or ambiguous; no passing claim is possible."
        for anchor_id, without in ablations.items():
            if personal.get(entity_id) is not None and without.get(entity_id) is not None:
                row["anchor_removals"].append({
                    "anchor": anchor_names[anchor_id],
                    "rank_drop": personal[entity_id] - without[entity_id],
                })
        output.append(row)
    suggestions = []
    candidate_ids = {row["entity_id"] for row in output}
    for entity in sorted(context.universe, key=lambda item: personal.get(item.entity_id) or 0, reverse=True):
        decision = decide(personal_percentile=personal.get(entity.entity_id),
                          city_percentile=context.baseline.get(entity.entity_id), policy=selected_policy)
        if entity.entity_id not in candidate_ids and decision.status == "supported":
            suggestions.append({"name": entity.name, "entity_id": entity.entity_id,
                                "reason": "Suggested from this comparison set; the source agent must resubmit its choice.",
                                "approval_status": "suggested"})
        if len(suggestions) == 3:
            break
    # Broad graph tags describe related entities, not necessarily this person.
    # Declared anchors and measured omission tests are the explanation evidence.
    tags = []  # Retained as an empty compatibility field.
    mode = context.mode
    if mode == "DEMO":
        for step in trace:
            step["state"] = "demo"
    return {
        "source": {"mode": mode, "label": "DEMO — SYNTHETIC" if mode == "DEMO" else "QLOO LIVE",
                   "detail": "Synthetic catalog and scores; no provider requests." if mode == "DEMO" else "Qloo API evidence, with a private server cache of up to five minutes. Ranks require complete coverage."},
        "city": context.city, "policy_id": policy_id, "policy": asdict(selected_policy),
        "anchors": [{"name": name, "id": entity.entity_id if entity else None,
                     "resolved_name": entity.name if entity else None,
                     "resolution": "resolved" if entity else "unverified"}
                    for name, entity in zip(anchors, resolved_anchors)],
        "candidates": output, "repairs": suggestions, "tags": tags, "trace": trace,
        "fixed_universe_count": len(context.ids), "comparison_fingerprint": context.fingerprint,
        "scoring_coverage": {"scored": sum(value is not None for value in scored.values()),
                             "required": len(context.ids), "complete": ranks_available},
        "baseline_available": all(value is not None for value in context.baseline.values()) and bool(context.ids),
        "limitations": [
            "Ranks are relative to this comparison set; they do not establish an individual's enjoyment.",
            "Receipt's thresholds are prototype policy. Generic means insufficient measured rank lift.",
            "Restaurant and radius checks use returned tags and coordinates; missing metadata stays unverified.",
            "Distance is straight-line distance from the supplied point, not walking or driving time.",
            "Hours, prices, accessibility, safety and availability are not verified.",
            "Resubmission is another check against the same evaluator, not independent proof of quality.",
            "A browser confirmation records an explicit action; reviewer identity is not verified.",
        ],
        "constraints": context.scope.public(),
    }


def _verdict(result):
    if result["approval_eligible"]:
        return {"title": "Ready for review", "detail": "Every submitted place clears the recorded policy."}
    if any(row["status"] == "unverified" for row in result["candidates"]):
        return {"title": "Evidence incomplete", "detail": "Every proposed place remains visible, including unverified picks."}
    return {"title": "Revision needed", "detail": "The policy flagged a mismatch or insufficient taste lift."}


def _validate(anchors, candidates, city, policy):
    if policy not in POLICIES:
        raise AuditError("Unknown policy.")
    if not 2 <= len(anchors) <= 5 or not 1 <= len(candidates) <= 6:
        raise AuditError("Use two to five anchors and one to six places.")
    for values in (anchors, candidates):
        normalized = [normalize_name(value) for value in values]
        if any(not value or len(value) > 200 for value in values) or not all(normalized):
            raise AuditError("Names must be nonempty and at most 200 characters.")
        if len(set(normalized)) != len(normalized):
            raise AuditError("Use distinct names.")
    if not city.strip():
        raise AuditError("A city is required.")


def _entry(audit_id, owner):
    _discard_expired()
    entry = PENDING.get(audit_id)
    if not entry or entry["owner"] != owner:
        raise AuditError("This audit expired or is unavailable in this session.")
    return entry


def _discard_expired():
    for audit_id, entry in list(PENDING.items()):
        if entry["result"]["expires_at"] < time.time():
            PENDING.pop(audit_id, None)
