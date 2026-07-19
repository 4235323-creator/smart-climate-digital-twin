"""Общая логика для OSM-провайдеров (Nominatim, Photon) — оба говорят на языке OSM-тегов."""
from __future__ import annotations

from ...domain.models import LocationType

_MALL_HINTS = {"mall", "shopping_centre", "marketplace", "department_store"}
_BUSINESS_CENTER_HINTS = {"office", "commercial", "coworking_space"}
_BUSINESS_HINTS = {"shop", "company", "industrial", "retail"}
_ADDRESS_HINTS = {"house", "building"}
_STREET_HINTS = {"highway", "residential", "road"}
_COUNTRY_HINTS = {"country"}
_REGION_HINTS = {"state", "region", "province", "county"}
_CITY_HINTS = {"city", "administrative"}
_TOWN_HINTS = {"town"}
_VILLAGE_HINTS = {"village", "hamlet"}


def infer_location_type(osm_class: str | None, osm_type: str | None, address: dict) -> LocationType:
    """Определяет LocationType по OSM class/type + составу address dict, без каких-либо словарей объектов."""
    osm_class = (osm_class or "").lower()
    osm_type = (osm_type or "").lower()
    tags = {osm_class, osm_type}

    if tags & _MALL_HINTS:
        return LocationType.MALL
    if tags & _BUSINESS_CENTER_HINTS:
        return LocationType.BUSINESS_CENTER
    if tags & _BUSINESS_HINTS:
        return LocationType.BUSINESS
    if address.get("house_number") or tags & _ADDRESS_HINTS:
        return LocationType.ADDRESS
    if tags & _STREET_HINTS or address.get("road"):
        return LocationType.STREET
    if tags & _VILLAGE_HINTS or address.get("village") or address.get("hamlet"):
        return LocationType.VILLAGE
    if tags & _TOWN_HINTS or address.get("town"):
        return LocationType.TOWN
    if address.get("city"):
        return LocationType.CITY
    if tags & _REGION_HINTS or address.get("state"):
        return LocationType.REGION
    if tags & _COUNTRY_HINTS or (address.get("country") and len(address) == 2):
        return LocationType.COUNTRY
    return LocationType.UNKNOWN


def extract_region(address: dict) -> str | None:
    return address.get("state") or address.get("region") or address.get("province") or address.get("county")


def extract_city(address: dict) -> str | None:
    return (
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("hamlet")
        or address.get("municipality")
    )
