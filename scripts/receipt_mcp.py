"""Local stdio MCP bridge. Model credentials remain in the user's AI client."""

import argparse
from http.cookiejar import CookieJar
import json
import time
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPCookieProcessor, HTTPRedirectHandler, Request, build_opener


class Venue(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=100)
    latitude: float = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: float = Field(ge=-180, le=180, allow_inf_nan=False)
    radius_m: int = Field(default=5000, ge=100, le=50000)


class Constraints(BaseModel):
    model_config = ConfigDict(extra="forbid")
    category: Literal["any", "restaurant"] = "restaurant"
    venue: Venue | None = None


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ValueError("Receipt returned an unexpected redirect.")


class ReceiptClient:
    def __init__(self, base_url):
        parsed = urlsplit(base_url)
        if (parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username
                or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/")
                or (parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost", "::1"))):
            raise ValueError("Use an HTTPS Receipt origin, or HTTP on localhost.")
        self.base_url = base_url.rstrip("/")
        self.http = build_opener(NoRedirect, HTTPCookieProcessor(CookieJar()))
        self.snapshots = {}

    def request(self, path, payload=None):
        req = Request(self.base_url + path, data=json.dumps(payload).encode() if payload is not None else None,
                      headers={"Content-Type": "application/json", "Accept": "application/json"})
        try:
            with self.http.open(req, timeout=50) as response:
                raw = response.read(2_000_001)
                if len(raw) > 2_000_000:
                    raise ValueError("Receipt response exceeded the bridge limit.")
                return json.loads(raw)
        except HTTPError as exc:
            # Only the application's structured error is exposed, not headers,
            # request/session credentials, redirects or arbitrary provider bodies.
            try:
                detail = json.loads(exc.read(131072)).get("detail")
            except (ValueError, AttributeError):
                detail = None
            raise ValueError(str(detail or f"Receipt returned HTTP {exc.code}.")) from None
        except URLError:
            raise ValueError("Cannot connect to Receipt. Check the configured origin and server status.") from None

    def audit(self, payload):
        parent = payload.get("revision_of")
        if parent:
            if parent not in self.snapshots:
                raise ValueError("This bridge did not create that original audit. Start a new check.")
            original = self.snapshots[parent]
            # Preserve context automatically; never let a model silently change it.
            fixed = ("anchors", "city", "policy", "constraints", "demo", "anchor_selections")
            if any(key in payload and payload[key] != original.get(key) for key in fixed):
                raise ValueError("A revision must keep the original tastes, identity choices, city, strictness and constraints.")
            payload = {**{key: original[key] for key in fixed}, **payload}
        else:
            payload = {"policy": "personalized", "demo": False, "constraints": {}, "anchor_selections": {}, **payload}
        job = self.request("/api/jobs/audit", payload)
        deadline = time.monotonic() + 190
        while job["status"] in ("queued", "running"):
            if time.monotonic() > deadline:
                self.request("/api/jobs/" + job["job_id"] + "/cancel", {})
                raise ValueError("Receipt exceeded the bridge time limit.")
            time.sleep(.4)
            job = self.request("/api/jobs/" + job["job_id"])
        if job["status"] != "complete":
            raise ValueError(job.get("error") or "Receipt could not finish the check.")
        result = job["result"]
        self.snapshots[result["audit_id"]] = payload
        # Bounded client-session memory, matching the application's short lifetime.
        while len(self.snapshots) > 100:
            self.snapshots.pop(next(iter(self.snapshots)))
        return result


def create_server(client):
    from mcp.server.fastmcp import FastMCP
    server = FastMCP("Receipt", instructions="Audit recommendations against Qloo. Do not call suggested alternatives independently validated. Approval belongs to the browser user, never this tool.")

    @server.tool()
    def resolve_tastes(anchors: list[str]) -> dict:
        """Find exact/alias identities. Ask the user to choose if a query has multiple options; never auto-pick a title."""
        return client.request("/api/anchors/resolve", {"anchors": anchors})

    @server.tool()
    def audit_recommendations(anchors: list[str], candidates: list[str], city: str,
                              policy: Literal["standard", "personalized", "verified_only"] = "personalized", constraints: Constraints | None = None,
                              anchor_selections: dict | None = None, demo: bool = False) -> dict:
        """Check 1–6 proposed places for 2–5 tastes. Returns critique and suggested alternatives. Live requires configured Qloo; demo is explicitly synthetic. Keep proposals realistic; unverified does not mean nonexistent."""
        return client.audit({"anchors": anchors, "candidates": candidates, "city": city, "policy": policy,
                             "constraints": (constraints or Constraints()).model_dump(), "anchor_selections": anchor_selections or {}, "demo": demo})

    @server.tool()
    def revise_recommendations(audit_id: str, candidates: list[str]) -> dict:
        """Re-audit a changed list. Automatically freezes the original tastes, identity choices, comparison set and constraints. Cannot approve or book anything."""
        return client.audit({"revision_of": audit_id, "candidates": candidates})

    return server


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="https://receipt.91.99.162.43.sslip.io")
    args = parser.parse_args()
    create_server(ReceiptClient(args.base_url)).run(transport="stdio")
