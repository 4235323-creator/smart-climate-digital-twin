"""HERE Maps Geocoding & Search — приоритет №5, последний в каскаде. Требует API-ключ."""
from __future__ import annotations

from ...domain.models import LocationResult, LocationType
from .base import GeocodingProvider, GeocodingProviderError

_GEOCODE_URL = "https://geocode.search.hereapi.com/v1/geocode"
_REVERSE_URL = "https://revgeocode.search.hereapi.com/v1/revgeocode"

_RESULT_TYPE_MAP = {
    "houseNumber": LocationType.ADDRESS,
    "street": LocationType.STREET,
    "locality": LocationType.CITY,
    "administrativeArea": LocationType.REGION,
    "country": LocationType.COUNTRY,
}


class HereMapsProvider(GeocodingProvider):
    """Последний резервный провайдер каскада — используется, если все остальные недоступны."""

    name = "HERE Maps"

    @property
    def requires_api_key(self) -> bool:
        return True

    async def geocode(self, query: str, limit: int = 5) -> list[LocationResult]:
        response = await self._http.get(
            _GEOCODE_URL, params={"q": query, "apiKey": self._api_key, "limit": limit}
        )
        self._raise_for_status(response)
        items = response.json().get("items", [])
        if not items:
            raise GeocodingProviderError(f"{self.name}: пустой результат для '{query}'")
        return [self._to_location_result(query, item) for item in items]

    async def reverse_geocode(self, latitude: float, longitude: float) -> LocationResult:
        response = await self._http.get(
            _REVERSE_URL,
            params={"at": f"{latitude},{longitude}", "apiKey": self._api_key},
        )
        self._raise_for_status(response)
        items = response.json().get("items", [])
        if not items:
            raise GeocodingProviderError(f"{self.name}: обратное геокодирование не дало результата")
        return self._to_location_result(f"{latitude},{longitude}", items[0])

    def _to_location_result(self, query: str, item: dict) -> LocationResult:
        address = item.get("address", {})
        position = item["position"]
        categories = item.get("categories", [])
        location_type = _RESULT_TYPE_MAP.get(item.get("resultType", ""), LocationType.UNKNOWN)
        if location_type == LocationType.UNKNOWN and categories:
            primary_category = (categories[0].get("name") or "").lower()
            if "mall" in primary_category or "shopping" in primary_category:
                location_type = LocationType.MALL
            elif "office" in primary_category or "business" in primary_category:
                location_type = LocationType.BUSINESS_CENTER
            else:
                location_type = LocationType.BUSINESS
        return LocationResult(
            query=query,
            display_name=address.get("label", item.get("title", query)),
            name=item.get("title", address.get("label", query)),
            latitude=float(position["lat"]),
            longitude=float(position["lng"]),
            country=address.get("countryName"),
            country_code=address.get("countryCode"),
            region=address.get("state") or address.get("county"),
            city=address.get("city"),
            address=address.get("label"),
            postcode=address.get("postalCode"),
            location_type=location_type,
            provider=self.name,
            raw=item,
        )
