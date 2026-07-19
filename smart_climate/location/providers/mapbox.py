"""Mapbox Geocoding API — приоритет №4. Требует access token пользователя."""
from __future__ import annotations

from urllib.parse import quote

from ...domain.models import LocationResult, LocationType
from .base import GeocodingProvider, GeocodingProviderError

_BASE_URL = "https://api.mapbox.com/geocoding/v5/mapbox.places"

_TYPE_MAP = {
    "poi": LocationType.BUSINESS,
    "address": LocationType.ADDRESS,
    "street": LocationType.STREET,
    "place": LocationType.CITY,
    "locality": LocationType.TOWN,
    "neighborhood": LocationType.CITY,
    "region": LocationType.REGION,
    "postcode": LocationType.ADDRESS,
    "country": LocationType.COUNTRY,
}


class MapboxProvider(GeocodingProvider):
    """Геокодинг Mapbox — хорошее покрытие POI (включая ТРЦ/бизнес-центры)."""

    name = "Mapbox"

    @property
    def requires_api_key(self) -> bool:
        return True

    async def geocode(self, query: str, limit: int = 5) -> list[LocationResult]:
        encoded = quote(query)
        response = await self._http.get(
            f"{_BASE_URL}/{encoded}.json",
            params={"access_token": self._api_key, "limit": limit},
        )
        self._raise_for_status(response)
        features = response.json().get("features", [])
        if not features:
            raise GeocodingProviderError(f"{self.name}: пустой результат для '{query}'")
        return [self._to_location_result(query, feature) for feature in features]

    async def reverse_geocode(self, latitude: float, longitude: float) -> LocationResult:
        response = await self._http.get(
            f"{_BASE_URL}/{longitude},{latitude}.json",
            params={"access_token": self._api_key},
        )
        self._raise_for_status(response)
        features = response.json().get("features", [])
        if not features:
            raise GeocodingProviderError(f"{self.name}: обратное геокодирование не дало результата")
        return self._to_location_result(f"{latitude},{longitude}", features[0])

    def _to_location_result(self, query: str, feature: dict) -> LocationResult:
        lon, lat = feature["center"]
        context = {entry["id"].split(".")[0]: entry["text"] for entry in feature.get("context", [])}
        location_type = LocationType.UNKNOWN
        for mapbox_type in feature.get("place_type", []):
            if mapbox_type in _TYPE_MAP:
                location_type = _TYPE_MAP[mapbox_type]
                break
        return LocationResult(
            query=query,
            display_name=feature.get("place_name", query),
            name=feature.get("text", feature.get("place_name", query)),
            latitude=float(lat),
            longitude=float(lon),
            country=context.get("country"),
            country_code=None,
            region=context.get("region"),
            city=context.get("place"),
            address=feature.get("place_name"),
            postcode=context.get("postcode"),
            location_type=location_type,
            provider=self.name,
            raw=feature,
        )
