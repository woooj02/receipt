"""Create a private, sanitized Qloo integration report. Never enables the baseline."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.context import prepare, score_map
from app.evaluation import complete_percentiles
from app.qloo import CACHE, QlooClient, QlooError
from app.runtime import WorkTimeout, work_budget
from app.scope import Scope, Venue


def collect(anchors, places, city, scope):
    if not QlooClient().configured:
        raise QlooError("QLOO_API_KEY is not configured. No requests were made.")
    started = time.monotonic()
    with work_budget(180):
        context = prepare(city, places, False, scope)
        resolved = [context.client.resolve_anchor(name) for name in anchors]
        ids = [item.entity_id for item in resolved if item]
        personal = score_map(context.client.score_places(ids, context.ids, city), context.ids) if len(set(ids)) == len(anchors) else dict.fromkeys(context.ids)
        personal_ranks = complete_percentiles(personal)
        baseline_ready, repeat_stable, baseline_error = False, False, None
        baseline_scored = 0
        try:
            baseline = score_map(context.client.score_city_baseline(context.ids, city), context.ids)
            baseline_scored = sum(value is not None for value in baseline.values())
            CACHE.clear()
            repeated = score_map(context.client.score_city_baseline(context.ids, city), context.ids)
            complete = all(value is not None for value in complete_percentiles(baseline).values()) and len(baseline) >= 10
            repeat_stable = complete and all(repeated[item] is not None and abs(baseline[item] - repeated[item]) <= 1e-6 for item in baseline)
            baseline_ready = repeat_stable and len(set(baseline.values())) > 1
            if not baseline_scored:
                baseline_error = "The no-interest response supplied no affinity values. Taste Lift cannot be computed."
        except QlooError as exc:
            baseline_error = str(exc)
        return {
            "checked_at": datetime.now(timezone.utc).isoformat(), "source": "LIVE QLOO PROBE",
            "city": city, "constraints": scope.public(), "anchors_requested": anchors,
            "anchors_resolved": len(set(ids)), "places_requested": places,
            "places_resolved": sum(context.resolve(name) is not None for name in places),
            "comparison_count": len(context.ids), "comparison_fingerprint": context.fingerprint,
            "personal_scoring_complete": any(value is not None for value in personal_ranks.values()),
            "personal_scored_count": sum(value is not None for value in personal.values()),
            "reference_policy": "Taste-independent city discovery; no cultural-interest signal.",
            "baseline_scored_count": baseline_scored,
            "baseline_numeric_checks_passed": baseline_ready, "baseline_repeat_stable": repeat_stable,
            "baseline_error": baseline_error, "elapsed_seconds": round(time.monotonic() - started, 2),
            "manual_review_required": True,
            "baseline_enabled_by_probe": False,
            "note": "Complete, stable scores are necessary but do not establish semantic comparability. Review the baseline interpretation before enabling Taste Lift.",
        }


def write_private(report, prefix):
    directory = Path(__file__).resolve().parents[1] / "data"
    directory.mkdir(mode=0o700, exist_ok=True)
    destination = directory / (prefix + "-" + secrets.token_hex(6) + ".json")
    with destination.open("x") as output:
        json.dump(report, output, indent=2, allow_nan=False)
    destination.chmod(0o600)
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--city", required=True)
    parser.add_argument("--anchor", action="append", required=True)
    parser.add_argument("--place", action="append", required=True)
    parser.add_argument("--category", choices=("restaurant", "any"), default="restaurant")
    parser.add_argument("--latitude", type=float)
    parser.add_argument("--longitude", type=float)
    parser.add_argument("--radius-m", type=int, default=5000)
    parser.add_argument("--venue-label", default="Supplied venue point")
    args = parser.parse_args()
    if not 2 <= len(args.anchor) <= 5 or not 1 <= len(args.place) <= 6:
        parser.error("Use 2–5 anchors and 1–6 places.")
    if (args.latitude is None) != (args.longitude is None):
        parser.error("Provide both venue coordinates.")
    venue = Venue(args.venue_label, args.latitude, args.longitude, args.radius_m) if args.latitude is not None else None
    try:
        report = collect(args.anchor, args.place, args.city, Scope(args.category, venue))
    except (QlooError, WorkTimeout, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    path = write_private(report, "live-probe")
    print("Private report: " + str(path))
    print("Personal scoring complete: " + str(report["personal_scoring_complete"]))
    print("Baseline numeric checks: " + str(report["baseline_numeric_checks_passed"]) + "; manual interpretation review still required.")
    return 0 if report["personal_scoring_complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
