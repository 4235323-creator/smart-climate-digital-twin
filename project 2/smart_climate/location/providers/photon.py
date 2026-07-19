"""Photon (Komoot) — приоритет №2. OSM-based, бесплатно, без ключа, быстрее Nominatim."""
from __future__ import annotations

from ...domain.models import LocationResult
from .base import GeocodingProvider, GeocodingProviderError
from ._osm_common import infer_location_type

_BASE_URL = "https://photon.komoot.io/api"
_REVERSE_URL = "https://photon.komoot.io/reverse"


class PhotonProvider(GeocodingProvider):
    """Свободный текстовый поиск + reverse geocoding через Photon (GeoJSON API)."""

    name = "Photon (Komoot)"

    async def geocode(self, query: str, limit: int = 5) -> list[LocationResult]:
        response = await self._http.get(_BASE_URL, params={"q": query, "limit": limit})
        self._raise_for_status(response)
        features = response.json().get("features", [])
        if not features:
            raise GeocodingProviderError(f"{self.name}: пустой результат для '{query}'")
        return [self._to_location_result(query, feature) for feature in features]

    async def reverse_geocode(self, latitude: float, longitude: float) -> LocationResult:
        response = await self._http.get(_REVERSE_URL, params={"lat": latitude, "lon": longitude})
        self._raise_for_status(response)
        features = response.json().get("features", [])
        if not features:
            raise GeocodingProviderError(f"{self.name}: обратное геокодирование не дало результата")
        return self._to_location_result(f"{latitude},{longitude}", features[0])

    @staticmethod
    def _to_location_result(query: str, feature: dict) -> LocationResult:
        props = feature.get("properties", {})
        lon, lat = feature["geometry"]["coordinates"]
        address_parts = [
            props.get("street"),
            props.get("housenumber"),
            props.get("postcode"),
            props.get("city"),
            props.get("country"),
        ]
        display_name = ", ".join(part for part in address_parts if part) or props.get("name", query)
        pseudo_address = {
            "city": props.get("city"),
            "town": props.get("city") if props.get("osm_value") == "town" else None,
            "village": props.get("city") if props.get("osm_value") == "village" else None,
            "state": props.get("state"),
            "country": props.get("country"),
            "house_number": props.get("housenumber"),
            "road": props.get("street"),
        }
        return LocationResult(
            query=query,
            display_name=display_name,
            name=props.get("name", display_name.split(",")[0]),
            latitude=float(lat),
            longitude=float(lon),
            country=props.get("country"),
            country_code=(props.get("countrycode") or "").upper() or None,
            region=props.get("state"),
            city=props.get("city"),
            address=display_name,
            postcode=props.get("postcode"),
            location_type=infer_location_type(props.get("osm_key"), props.get("osm_value"), pseudo_address),
            provider=PhotonProvider.name,
            raw=feature,
        )
