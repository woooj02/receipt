"""Small, server-only client for the Qloo hackathon API.

Only sanitised entity fields leave this module. Provider payloads are deliberately
not written to disk: the hackathon terms permit private caching, not publishing
Qloo response data in the repository.
"""

from __future__ import annotations

import json
import hashlib
import os
import math
import re
import time
import unicodedata
from threading import Lock
from dataclasses import dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .runtime import PrivateCache, remaining
from .guard import reserve_provider
from .scope import Scope


BASE_URL = "https://hackathon.api.qloo.com"
_REQUEST_LOCK = Lock()
_LAST_REQUEST = 0.0
CACHE = PrivateCache()
ANCHOR_TYPES = ",".join(
    (
        "urn:entity:artist",
        "urn:entity:movie",
        "urn:entity:book",
        "urn:entity:tv_show",
        "urn:entity:podcast",
        "urn:entity:brand",
    )
)


class QlooError(RuntimeError):
    """A safe provider error suitable for a public API response."""


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, request, response, code, message, headers, target):
        raise QlooError("Qloo returned an unexpected redirect.")


urlopen = build_opener(NoRedirect).open


@dataclass(frozen=True)
class Entity:
    entity_id: str
    name: str
    entity_type: str
    latitude: float | None = field(default=None, kw_only=True)
    longitude: float | None = field(default=None, kw_only=True)
    tags: tuple[str, ...] = field(default=(), kw_only=True)
    address: str | None = field(default=None, kw_only=True)
    image_url: str | None = field(default=None, kw_only=True)
    business_rating: float | None = field(default=None, kw_only=True)
    price_level: int | None = field(default=None, kw_only=True)
    keywords: tuple[str, ...] = field(default=(), kw_only=True)
    release_year: str | None = field(default=None, kw_only=True)


@dataclass(frozen=True)
class ScoredEntity(Entity):
    affinity: float | None
    contributions: tuple[tuple[str, float], ...] = field(default=(), kw_only=True)


class QlooClient:
    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.environ.get("QLOO_API_KEY")
        self.scope = Scope()
        self.restaurant_tag = None

    def configure_scope(self, scope):
        self.scope = scope
        if scope.category == "restaurant":
            payload = self._get("/v2/tags", {
                "filter.query": "restaurant", "filter.tag.types": "urn:tag:category:place", "take": "50",
            })
            tags = self._results(payload, "tags")
            matches = {str(tag.get("tag_id") or tag.get("id")) for tag in tags
                       if normalize_name(self._name(tag)) in ("restaurant", "restaurants")
                       and str(tag.get("tag_id") or tag.get("id") or "").startswith("urn:tag:category:place:")}
            if len(matches) != 1:
                raise QlooError("A unique restaurant category tag could not be verified.")
            self.restaurant_tag = next(iter(matches))

    def _place_filters(self, city):
        scope = getattr(self, "scope", Scope())
        if scope.venue:
            result = {"filter.location": f"POINT({scope.venue.longitude} {scope.venue.latitude})",
                      "filter.location.radius": str(scope.venue.radius_m)}
        else:
            result = {"filter.location.query": city, "filter.location.radius": "0"}
        if scope.category == "restaurant":
            result["filter.tags"] = self.restaurant_tag
        return result

    @property
    def configured(self) -> bool:
        return bool(self.api_key)

    @property
    def baseline_verified(self) -> bool:
        # Enable only after the live probe verifies complete, comparable scores.
        return os.environ.get("QLOO_BASELINE_VERIFIED") == "1"

    @property
    def reference_panel_enabled(self):
        return os.environ.get("RECEIPT_REFERENCE_PANEL", "1") == "1"

    def anchor_options(self, name: str) -> list[Entity]:
        return self._matches(name, ANCHOR_TYPES)

    def resolve_anchor(self, name: str, selected_id: str | None = None) -> Entity | None:
        matches = self.anchor_options(name)
        if selected_id:
            return next((item for item in matches if item.entity_id == selected_id), None)
        return matches[0] if len(matches) == 1 else None

    def resolve_place(self, name: str, city: str) -> Entity | None:
        # A city is an ambiguity aid during search. The final Insights call also
        # applies the city as a geospatial filter before any score is accepted.
        return self._resolve(name, "urn:entity:place", city=city)

    def score_places(
        self, anchor_ids: list[str], candidate_ids: list[str], city: str
    ) -> list[ScoredEntity]:
        return self._score_pages(
            {
                "filter.type": "urn:entity:place",
                "signal.interests.entities": ",".join(anchor_ids),
                "filter.results.entities": ",".join(candidate_ids),
                **self._place_filters(city),
                "feature.explainability": "true",
                "sort_by": "affinity",
            },
            candidate_ids,
        )

    def city_reference_places(self, city: str) -> list[ScoredEntity]:
        """Return a taste-independent city discovery pool for a fixed-universe test.

        Location is a documented Insights filter. Whether the hackathon provider
        returns a useful city-only ranking is deliberately verified before the UI
        publishes a Taste Lift value.
        """
        payload = self._get("/v2/insights", {
            "filter.type": "urn:entity:place",
            **self._place_filters(city),
            "sort_by": "affinity",
            "take": "50",
        })
        return [self._scored(item) for item in self._results(payload, "entities")]

    def score_city_baseline(self, candidate_ids: list[str], city: str) -> list[ScoredEntity]:
        """Score the same universe without cultural taste signals.

        This intentionally uses no personal signal. The caller must treat absent
        affinity as an unavailable baseline, not a zero or a generic verdict.
        """
        return self._score_pages(
            {
                "filter.type": "urn:entity:place",
                "filter.results.entities": ",".join(candidate_ids),
                **self._place_filters(city),
                "sort_by": "affinity",
            },
            candidate_ids,
        )

    def _score_pages(self, params: dict[str, str], candidate_ids: list[str]) -> list[ScoredEntity]:
        # Keep the full ID filter constant across pages; chunking would change the
        # scoring context. Fifty is the page size, not a universe-size limit.
        expected = set(candidate_ids)
        found: dict[str, ScoredEntity] = {}
        for page in range(1, math.ceil(len(expected) / 50) + 1):
            payload = self._get("/v2/insights", {**params, "take": "50", "page": str(page)})
            rows = self._results(payload, "entities")
            for row in rows:
                item = self._scored(row)
                if item.entity_id not in expected or item.entity_id in found:
                    raise QlooError("Qloo returned unexpected or repeated entities in the fixed universe.")
                found[item.entity_id] = item
            if len(rows) < 50:
                break
        return list(found.values())

    def _resolve(self, name: str, entity_types: str, city: str | None = None) -> Entity | None:
        confirmed = self._matches(name, entity_types, city)
        return confirmed[0] if len(confirmed) == 1 else None

    def _matches(self, name: str, entity_types: str, city: str | None = None) -> list[Entity]:
        params = {"query": name, "types": entity_types, "take": "8"}
        scope = getattr(self, "scope", Scope())
        if city and scope.venue:
            # The hackathon Search service requires lat,lon even though the
            # newer reference also lists WKT. Insights uses longitude-first WKT.
            params["filter.location"] = f"{scope.venue.latitude},{scope.venue.longitude}"
            params["filter.radius"] = str(scope.venue.radius_m / 1609.344)
        elif city:
            params["filter.address"] = city.split(",")[0].strip()
        payload = self._get("/search", params)
        matches = self._results(payload)
        confirmed: dict[str, Entity] = {}
        for match in matches:
            entity = self._entity(match)
            if not entity or entity.entity_type not in entity_types.split(","):
                continue
            if normalize_name(entity.name) != normalize_name(name):
                continue
            if city and not scope.venue:
                properties = match.get("properties") if isinstance(match.get("properties"), dict) else {}
                geocode = properties.get("geocode") if isinstance(properties.get("geocode"), dict) else {}
                address = properties.get("address") or ""
                city_name = normalize_name(city.split(",")[0])
                address_text = " " + normalize_name(str(address)) + " "
                if normalize_name(str(geocode.get("city", ""))) != city_name and (" " + city_name + " ") not in address_text:
                    continue
            confirmed[entity.entity_id] = entity
        # Ambiguous names require explicit disambiguation; picking the first
        # search result is not evidence that it is the intended place or title.
        return list(confirmed.values())

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        remaining()
        identity = hashlib.sha256((self.api_key or "").encode()).hexdigest()
        cache_key = (identity, path, tuple(sorted(params.items())))
        cached = CACHE.get(cache_key)
        if cached is not None:
            return cached
        payload = self._fetch(path, params)
        CACHE.put(cache_key, payload)
        return payload

    def _fetch(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        if not self.api_key:
            raise QlooError("Qloo is not configured on this server.")
        query = urlencode(params, safe=",")
        request = Request(
            f"{BASE_URL}{path}?{query}",
            headers={"X-Api-Key": self.api_key, "Accept": "application/json"},
            method="GET",
        )
        global _LAST_REQUEST
        for attempt in range(3):
            remaining()
            with _REQUEST_LOCK:
                delay = max(0, 0.25 - (time.monotonic() - _LAST_REQUEST))
                time.sleep(min(delay, remaining()))
                _LAST_REQUEST = time.monotonic()
            try:
                reserve_provider("qloo")
                with urlopen(request, timeout=remaining(15)) as response:  # noqa: S310 - fixed host
                    payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict) or payload.get("success") is False:
                    raise QlooError("Qloo returned an unsuccessful response.")
                return payload
            except HTTPError as exc:
                if path == "/search" and exc.code == 404:
                    return {"results": []}
                if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(min(0.5 * (2 ** attempt), remaining()))
                    continue
                # Never forward a provider response body; it can echo a key or
                # arbitrary text into the public error response.
                raise QlooError(f"Qloo request failed (HTTP {exc.code}).") from exc
            except (URLError, TimeoutError, json.JSONDecodeError, UnicodeError) as exc:
                raise QlooError("Qloo could not be reached or returned invalid JSON.") from exc
        raise QlooError("Qloo request could not be completed.")

    @staticmethod
    def _results(payload: dict[str, Any], key: str | None = None) -> list[dict[str, Any]]:
        results = payload.get("results", [])
        if isinstance(results, dict):
            results = results.get(key or "entities", [])
        return [row for row in results if isinstance(row, dict)] if isinstance(results, list) else []

    @staticmethod
    def _name(item: dict[str, Any]) -> str:
        properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
        return str(item.get("name") or properties.get("name") or item.get("title") or "").strip()

    def _entity(self, item: dict[str, Any]) -> Entity | None:
        entity_id = str(item.get("entity_id") or item.get("id") or item.get("uuid") or "").strip()
        name = self._name(item)
        entity_type = item.get("types") or item.get("subtype") or item.get("type") or item.get("entity_type") or "urn:entity:unknown"
        if isinstance(entity_type, list):
            entity_type = entity_type[0] if entity_type else "urn:entity:unknown"
        properties = item.get("properties") if isinstance(item.get("properties"), dict) else {}
        location = item.get("location") or properties.get("location") or {}
        location = location if isinstance(location, dict) else {}
        latitude = _coordinate(location.get("lat", location.get("latitude")), 90)
        longitude = _coordinate(location.get("lon", location.get("longitude")), 180)
        raw_tags = item.get("tags") or properties.get("tags") or []
        tag_ids = []
        for tag in raw_tags if isinstance(raw_tags, list) else []:
            tag_id = (tag.get("tag_id") or tag.get("id")) if isinstance(tag, dict) else tag
            if isinstance(tag_id, str) and tag_id.startswith("urn:tag:"):
                tag_ids.append(tag_id)
        image = properties.get("image")
        image_url = safe_image_url(image.get("url")) if isinstance(image, dict) else None
        keywords = properties.get("keywords")
        rating = _bounded_number(properties.get("business_rating"), 5)
        price = properties.get("price_level")
        return Entity(entity_id, name, str(entity_type), latitude=latitude, longitude=longitude,
                      tags=tuple(sorted(set(tag_ids))), address=_text(properties.get("address"), 300),
                      image_url=image_url, business_rating=rating,
                      release_year=_release_year(properties),
                      price_level=price if type(price) is int and 0 <= price <= 4 else None,
                      keywords=tuple(k[:80] for k in keywords[:8] if isinstance(k, str))
                      if isinstance(keywords, list) else ()) if entity_id and name else None

    def _scored(self, item: dict[str, Any]) -> ScoredEntity:
        entity = self._entity(item)
        if not entity:
            raise QlooError("Qloo returned an entity without an identifier or name.")
        query = item.get("query") if isinstance(item.get("query"), dict) else {}
        raw_affinity = query.get("affinity", item.get("affinity"))
        try:
            affinity = float(raw_affinity) if raw_affinity is not None else None
        except (TypeError, ValueError):
            affinity = None
        if affinity is not None and (not math.isfinite(affinity) or not 0 <= affinity <= 1 or isinstance(raw_affinity, bool)):
            affinity = None
        block = query.get("explainability")
        signals = block.get("signal.interests.entities", []) if isinstance(block, dict) and not block.get("warning") else []
        contributions = []
        for row in signals if isinstance(signals, list) else []:
            if not isinstance(row, dict):
                continue
            score = _bounded_number(row.get("score"), 1)
            if isinstance(row.get("entity_id"), str) and score is not None:
                contributions.append((row["entity_id"], score))
        return ScoredEntity(**entity.__dict__, affinity=affinity, contributions=tuple(contributions))


def safe_image_url(value):
    if not isinstance(value, str) or len(value) > 1500:
        return None
    try:
        parsed = urlsplit(value)
        return value if (parsed.scheme == "https" and parsed.hostname == "images.qloo.com"
                         and parsed.port in (None, 443) and not parsed.username and not parsed.password) else None
    except ValueError:
        return None


def _text(value, limit):
    return value[:limit] if isinstance(value, str) and value.strip() else None


def _bounded_number(value, maximum):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) and 0 <= value <= maximum else None


def normalize_name(value: str) -> str:
    value = unicodedata.normalize("NFKD", value).casefold()
    value = "".join(char for char in value if not unicodedata.combining(char))
    words = re.findall(r"[^\W_]+", value.replace("&", " and "), flags=re.UNICODE)
    if len(words) > 1 and words[0] == "the":
        words = words[1:]
    return " ".join(words)


def _release_year(properties):
    for key in ("release_year", "release_date", "publication_date", "year"):
        match = re.match(r"^(\d{4})(?:\D|$)", str(properties.get(key, "")))
        if match:
            return match[1]
    return None


def taste_identity(anchors, selections=None):
    choices = {normalize_name(name): entity_id for name, entity_id in (selections or {}).items()}
    return frozenset((normalize_name(name), choices.get(normalize_name(name))) for name in anchors)


def _coordinate(value, bound):
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
        return number if math.isfinite(number) and -bound <= number <= bound else None
    except (ValueError, TypeError):
        return None
