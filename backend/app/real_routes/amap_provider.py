import asyncio
from collections.abc import Mapping
from decimal import Decimal, InvalidOperation

import httpx

from app.providers.errors import ProviderResponseError, ProviderTimeout
from app.real_routes.models import DrivingRouteResult, GeoPoint


class AmapDrivingRouteProvider:
    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = "https://restapi.amap.com/v5/direction/driving",
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 0.8,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url
        self._timeout_seconds = timeout_seconds
        self._client = client

    async def plan(
        self,
        origin: GeoPoint,
        destination: GeoPoint,
        waypoints: tuple[GeoPoint, ...],
    ) -> DrivingRouteResult:
        params = {
            "key": self._api_key,
            "origin": self._coordinate(origin),
            "destination": self._coordinate(destination),
            "alternative_route": "2",
            "show_fields": "cost",
        }
        if waypoints:
            params["waypoints"] = ";".join(self._coordinate(point) for point in waypoints)
        try:
            async with asyncio.timeout(self._timeout_seconds):
                response = await self._get(params)
            response.raise_for_status()
            payload = response.json()
            candidates = self._candidates(payload)
            if not candidates:
                raise ValueError("missing route candidates")
            return min(
                candidates,
                key=lambda item: (item.duration_seconds, item.distance_meters),
            )
        except (TimeoutError, httpx.TimeoutException) as error:
            raise ProviderTimeout("AMap route provider timed out") from error
        except (httpx.HTTPError, KeyError, TypeError, ValueError, InvalidOperation) as error:
            raise ProviderResponseError("AMap route provider response invalid") from error

    async def _get(self, params: dict[str, str]) -> httpx.Response:
        if self._client is not None:
            return await self._client.get(
                self._base_url,
                params=params,
                timeout=self._timeout_seconds,
            )
        async with httpx.AsyncClient(
            timeout=httpx.Timeout(self._timeout_seconds)
        ) as client:
            return await client.get(
                self._base_url,
                params=params,
                timeout=self._timeout_seconds,
            )

    @staticmethod
    def _coordinate(point: GeoPoint) -> str:
        return f"{point.longitude:f},{point.latitude:f}"

    @classmethod
    def _candidates(cls, payload: object) -> list[DrivingRouteResult]:
        if not isinstance(payload, Mapping) or payload.get("status") != "1":
            raise ValueError("provider rejected request")
        route = payload.get("route")
        if not isinstance(route, Mapping):
            raise ValueError("missing route")
        paths = route.get("paths")
        if not isinstance(paths, list):
            raise ValueError("missing paths")
        return [candidate for path in paths if (candidate := cls._candidate(path)) is not None]

    @classmethod
    def _candidate(cls, path: object) -> DrivingRouteResult | None:
        if not isinstance(path, Mapping):
            return None
        cost = path.get("cost")
        duration = cost.get("duration") if isinstance(cost, Mapping) else path.get("duration")
        steps = path.get("steps")
        if not isinstance(steps, list):
            return None
        polyline: list[GeoPoint] = []
        for step in steps:
            if not isinstance(step, Mapping) or not isinstance(step.get("polyline"), str):
                continue
            for coordinate in step["polyline"].split(";"):
                point = cls._polyline_point(coordinate)
                if not polyline or polyline[-1] != point:
                    polyline.append(point)
        distance_meters = int(path["distance"])
        duration_seconds = int(duration)
        if distance_meters <= 0 or duration_seconds <= 0 or len(polyline) < 2:
            return None
        return DrivingRouteResult(distance_meters, duration_seconds, tuple(polyline))

    @staticmethod
    def _polyline_point(value: str) -> GeoPoint:
        longitude, latitude = value.split(",", maxsplit=1)
        return GeoPoint(None, Decimal(longitude), Decimal(latitude))
