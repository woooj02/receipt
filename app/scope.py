"""Category and geographic constraints evaluated with ordinary code."""

from dataclasses import asdict, dataclass
import math


@dataclass(frozen=True)
class Venue:
    label: str
    latitude: float
    longitude: float
    radius_m: int = 5000

    def __post_init__(self):
        if not (math.isfinite(self.latitude) and -90 <= self.latitude <= 90
                and math.isfinite(self.longitude) and -180 <= self.longitude <= 180
                and 100 <= self.radius_m <= 50000):
            raise ValueError("Invalid venue coordinates or radius.")


@dataclass(frozen=True)
class Scope:
    category: str = "any"
    venue: Venue | None = None

    def __post_init__(self):
        if self.category not in ("any", "restaurant"):
            raise ValueError("Unsupported category.")

    def public(self):
        return asdict(self)


def distance_m(lat_a, lon_a, lat_b, lon_b):
    lat_a, lon_a, lat_b, lon_b = map(math.radians, (lat_a, lon_a, lat_b, lon_b))
    haversine = math.sin((lat_b - lat_a) / 2) ** 2 + math.cos(lat_a) * math.cos(lat_b) * math.sin((lon_b - lon_a) / 2) ** 2
    return 6371008.8 * 2 * math.asin(math.sqrt(min(1.0, max(0.0, haversine))))


def assess(entity, scope, restaurant_tag=None):
    """Return status, reason, and measured distance. Missing metadata is unknown."""
    if not entity:
        return "unverified", "The exact place could not be resolved.", None
    if scope.category == "restaurant":
        if not entity.tags:
            return "unverified", "Restaurant category metadata is unavailable.", None
        if not restaurant_tag or restaurant_tag not in entity.tags:
            return "ineligible", "This place does not carry the requested restaurant category.", None
    distance = None
    if scope.venue:
        if entity.latitude is None or entity.longitude is None:
            return "unverified", "Coordinates are unavailable; the venue radius cannot be checked.", None
        distance = distance_m(entity.latitude, entity.longitude, scope.venue.latitude, scope.venue.longitude)
        if distance > scope.venue.radius_m:
            return "ineligible", "This place lies outside the specified venue radius.", round(distance)
    return "eligible", None, round(distance) if distance is not None else None
