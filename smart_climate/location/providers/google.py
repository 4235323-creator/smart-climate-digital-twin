"""Google Geocoding API — приоритет №3. Требует API-ключ пользователя."""
from __future__ import annotations

from ...domain.models import LocationResult, LocationType
from .base import GeocodingProvider, GeocodingProviderError

_BASE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

_TYPE_MAP = {
    "shopping_mall": LocationType.MALL,
    "point_of_interest": LocationType.BUSINESS,
    "establishment": LocationType.BUSINESS,
    "premise": LocationType.BUILDING,
    "street_address": LocationType.ADDRESS,
    "route": LocationType.STREET,
    "locality": LocationType.CITY,
    "postal_town": LocationType.TOWN,
    "sublocality": LocationType.CITY,
    "administrative_area_level_1": LocationType.REGION,
    "administrative_area_level_2": LocationType.REGION,
    "country": LocationType.COUNTRY,
}


class GoogleGeocodingProvider(GeocodingProvider):
    """Коммерческий геокодинг Google — высокая точность для адресов и организаций."""

    name = "Google Geocoding"

    @property
    def requires_api_key(self) -> bool:
        return True

    async def geocode(self, query: str, limit: int = 5) -> list[LocationResult]:
        response = await self._http.get(
            _BASE_URL, params={"address": query, "key": self._api_key}
        )
        self._raise_for_status(response)
        payload = response.json()
        self._check_status(payload)
        return [self._to_location_result(query, item) for item in payload["results"][:limit]]

    async def reverse_geocode(self, latitude: float, longitude: float) -> LocationResult:
        response = await self._http.get(
            _BASE_URL,
            params={"latlng": f"{latitude},{longitude}", "key": self._api_key},
        )
        self._raise_for_status(response)
        payload = response.json()
        self._check_status(payload)
        return self._to_location_result(f"{latitude},{longitude}", payload["results"][0])

    def _check_status(self, payload: dict) -> None:
        status = payload.get("status")
        if status != "OK":
            raise GeocodingProviderError(f"{self.name}: статус {status}")

    def _to_location_result(self, query: str, item: dict) -> LocationResult:
        components = {c["types"][0]: c["long_name"] for c in item.get("address_components", []) if c.get("types")}
        location = item["geometry"]["location"]
        location_type = LocationType.UNKNOWN
        for google_type in item.get("types", []):
            if google_type in _TYPE_MAP:
                location_type = _TYPE_MAP[google_type]
                break
        return LocationResult(
            query=query,
            display_name=item.get("formatted_address", query),
            name=item.get("formatted_address", query).split(",")[0],
            latitude=float(location["lat"]),
            longitude=float(location["lng"]),
            country=components.get("country"),
            country_code=None,
            region=components.get("administrative_area_level_1"),
            city=components.get("locality") or components.get("postal_town"),
            address=item.get("formatted_address"),
            postcode=components.get("postal_code"),
            location_type=location_type,
            provider=self.name,
            raw=item,
        )
