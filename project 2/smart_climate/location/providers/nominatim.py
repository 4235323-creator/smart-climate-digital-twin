"""Nominatim (OpenStreetMap) — приоритет №1 в каскаде геокодинга. Бесплатно, без ключа."""
from __future__ import annotations

from ...domain.models import LocationResult, LocationType
from .base import GeocodingProvider, GeocodingProviderError
from ._osm_common import extract_city, extract_region, infer_location_type

_BASE_URL = "https://nominatim.openstreetmap.org"


class NominatimProvider(GeocodingProvider):
    """
    Ищет: страны, области, города, посёлки, сёла, улицы, дома,
    ТРЦ, бизнес-центры и предприятия (через свободный текстовый q=).
    """

    name = "Nominatim (OpenStreetMap)"

    async def geocode(self, query: str, limit: int = 5) -> list[LocationResult]:
        response = await self._http.get(
            f"{_BASE_URL}/search",
            params={
                "q": query,
                "format": "jsonv2",
                "addressdetails": 1,
                "limit": limit,
                "namedetails": 1,
            },
        )
        self._raise_for_status(response)
        payload = response.json()
        if not payload:
            raise GeocodingProviderError(f"{self.name}: пустой результат для '{query}'")
        return [self._to_location_result(query, item) for item in payload]

    async def reverse_geocode(self, latitude: float, longitude: float) -> LocationResult:
        response = await self._http.get(
            f"{_BASE_URL}/reverse",
            params={
                "lat": latitude,
                "lon": longitude,
                "format": "jsonv2",
                "addressdetails": 1,
            },
        )
        self._raise_for_status(response)
        payload = response.json()
        if "error" in payload:
            raise GeocodingProviderError(f"{self.name}: {payload['error']}")
        return self._to_location_result(f"{latitude},{longitude}", payload)

    @staticmethod
    def _to_location_result(query: str, item: dict) -> LocationResult:
        address = item.get("address", {})
        return LocationResult(
            query=query,
            display_name=item.get("display_name", query),
            name=item.get("name") or address.get("amenity") or item.get("display_name", query).split(",")[0],
            latitude=float(item["lat"]),
            longitude=float(item["lon"]),
            country=address.get("country"),
            country_code=(address.get("country_code") or "").upper() or None,
            region=extract_region(address),
            city=extract_city(address),
            address=item.get("display_name"),
            postcode=address.get("postcode"),
            location_type=infer_location_type(item.get("class"), item.get("type"), address),
            provider=NominatimProvider.name,
            raw=item,
        )
