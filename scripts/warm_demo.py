"""Warm the public example's Qloo cache through the existing bounded app API."""
import argparse
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8132")
    args = parser.parse_args()
    base = args.base_url.rstrip("/")
    origin = urlsplit(base)
    if (origin.scheme not in ("http", "https") or not origin.hostname or origin.username or origin.password
            or origin.path or origin.query or origin.fragment
            or (origin.scheme == "http" and origin.hostname not in ("127.0.0.1", "localhost", "::1"))):
        parser.error("Use HTTPS, or HTTP on localhost.")
    payload = {"anchors": ["Kendrick Lamar", "Everything Everywhere All at Once"],
        "candidates": ["Work & Class", "Tavernetta", "Forest Room 5"],
        "city": "Denver, Colorado", "policy": "personalized", "demo": False,
        "constraints": {"category": "restaurant", "venue": {"label": "The Mission Ballroom",
            "latitude": 39.776204, "longitude": -104.969168, "radius_m": 5000}}}
    request = Request(base + "/api/agent/audit", data=json.dumps(payload).encode(),
                      headers={"Content-Type": "application/json", "Accept": "application/json"})
    try:
        with urlopen(request, timeout=195) as response:
            result = json.load(response)
        if result.get("source", {}).get("mode") != "LIVE" or not result.get("scoring_coverage", {}).get("complete"):
            raise ValueError("Live scoring did not complete; cache warmth is unverified.")
    except HTTPError as exc:
        print(f"Warm-up stopped: app returned HTTP {exc.code}; no retry or confirmation.", file=sys.stderr)
        return 1
    except (URLError, ValueError, TimeoutError):
        print("Warm-up did not verify live scoring. Check app health and provider allowance.", file=sys.stderr)
        return 1
    print("Live example cache warmed; private provider cache expires after five minutes. No result confirmed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
