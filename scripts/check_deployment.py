"""Exercise the public HTTPS release without credentials or printing provider payloads.

This uses constructed validation inputs, not captured model recommendations.
It consumes the hosted app's bounded Qloo allowance; it never enables model calls.
"""

import argparse
from datetime import datetime, timezone
from http.cookiejar import CookieJar
import json
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPCookieProcessor, Request, build_opener


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    assert urlsplit(base).scheme == "https", "A certificate-verified HTTPS URL is required"
    cookies = CookieJar()
    client = build_opener(HTTPCookieProcessor(cookies))

    def request(path, payload=None, expected=200):
        data = json.dumps(payload).encode() if payload is not None else None
        headers = {"Accept": "application/json", "Origin": base}
        if data is not None:
            headers["Content-Type"] = "application/json"
        try:
            with client.open(Request(base + path, data=data, headers=headers), timeout=30) as response:
                assert response.status == expected, "Unexpected HTTP status"
                raw = response.read()
                return json.loads(raw) if "application/json" in response.headers.get("Content-Type", "") else raw
        except HTTPError as exc:
            if exc.code == expected:
                return None
            raise RuntimeError(f"HTTP {exc.code} from {path.split('/')[1:3]}") from None

    def run(kind, payload):
        job = request("/api/jobs/" + kind, payload, expected=202)
        deadline = time.monotonic() + 190
        while time.monotonic() < deadline:
            job = request("/api/jobs/" + job["job_id"])
            if job["status"] == "complete":
                return job["result"]
            assert job["status"] in ("queued", "running"), "Hosted job did not complete successfully"
            time.sleep(1)
        raise RuntimeError("Hosted run exceeded its time budget")

    health = request("/api/health")
    assert health["ok"] and health["qloo_agent_enabled"] and not health["live_agent_enabled"]
    assert b"Receipt" in request("/")
    assert request("/openapi.json")["info"]["version"] == "0.5.1"
    session = next(cookie for cookie in cookies if cookie.name == "receipt_session")
    assert session.secure and "HttpOnly" in session._rest and session._rest.get("SameSite") == "strict"
    for path in ("/.env", "/.git/config", "/data/live-workflows.json"):
        request(path, expected=404)
    print("PASS: public HTTPS, configured Qloo, model calls disabled, secure session, private paths denied", flush=True)

    brief = {
        "anchors": ["Kendrick Lamar", "Everything Everywhere All at Once"],
        "city": "Denver, Colorado", "demo": False, "policy": "standard",
        "constraints": {"category": "restaurant", "venue": {
            "label": "Mission Ballroom", "latitude": 39.776204,
            "longitude": -104.969168, "radius_m": 5000}},
    }
    first = run("audit", dict(brief, candidates=["Work & Class", "Tavernetta", "Receipt Validation Imaginary Bistro"]))
    assert first["source"]["mode"] == "LIVE" and first["scoring_coverage"]["complete"]
    assert first["reference_panel"]["available"]
    assert any(row["qloo_contributions"] and row["place"]["address"] for row in first["candidates"])
    assert not first["baseline_available"] and not first["approval_eligible"]
    assert first["candidates"][-1]["status"] == "unverified"
    names = [row["name"] for row in first["repairs"][:2]]
    assert len(names) == 2
    changed = run("audit", dict(brief, candidates=names, revision_of=first["audit_id"]))
    assert changed["comparison_fingerprint"] == first["comparison_fingerprint"]
    assert changed["approval_eligible"]
    review = request("/api/review/" + changed["audit_id"])
    receipt = request("/api/review/approve", {
        "audit_id": changed["audit_id"], "review_token": review["review_token"],
        "fingerprint": changed["fingerprint"],
    })
    assert receipt["approval_recorded"] and not receipt["approval_identity_verified"]
    assert receipt["audit_fingerprint"] == changed["fingerprint"]
    print(f"PASS: live audit ({first['scoring_coverage']['scored']} scored), frozen revision and exact-snapshot confirmation", flush=True)

    agent_brief = {key: value for key, value in brief.items() if key != "demo"}
    agent = run("agent", dict(agent_brief, mode="qloo", max_rounds=3, policy="personalized"))
    assert agent["source"]["mode"] == "LIVE" and "rules-based, no LLM" in agent["agent"]["label"]
    assert 1 <= len(agent["rounds"]) <= 3 and not agent["approval_recorded"]
    print(f"PASS: real-data rules agent, {len(agent['rounds'])} round(s), no automatic approval", flush=True)

    batch = run("batch", {
        "agent_name": "Constructed deployment validation — no model captures",
        "agent_version": "validation-v1", "prompt_version": "manual-validation",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        **{key: value for key, value in brief.items() if key != "anchors"},
        "profiles": [{"profile_id": name, "anchors": anchors,
                      "recommendations": ["Work & Class", "Tavernetta", "Forest Room 5"]}
                     for name, anchors in [("mixed", brief["anchors"]),
                                            ("pop", ["Taylor Swift", "Beyoncé"])]],
    })
    assert batch["source"]["mode"] == "LIVE" and batch["profile_count"] == 2
    assert batch["metrics"]["generic_rate"] is None
    assert batch["metrics"]["low_panel_lift_rate"] is not None
    assert len({profile["comparison_fingerprint"] for profile in batch["profiles"]}) == 1
    print("PASS: two constructed profiles, shared comparison set, unavailable generic rate stays unavailable", flush=True)


if __name__ == "__main__":
    main()
