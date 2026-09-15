from collections.abc import Sequence

from app.providers.errors import ProviderError
from app.real_routes.demo_coordinates import MAPPING_VERSION, demo_geo_points
from app.real_routes.models import RealRoadRoute
from app.real_routes.protocols import DrivingRouteProvider
from app.services.circuit_breaker import CircuitBreaker


class RealRoadRouteService:
    def __init__(
        self,
        provider: DrivingRouteProvider | None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        self._provider = provider
        self._circuit_breaker = circuit_breaker

    async def plan(self, node_ids: Sequence[str]) -> RealRoadRoute:
        identifiers = tuple(node_ids)
        if len(identifiers) < 2:
            raise ValueError("A real-road route requires at least two mapped nodes.")
        waypoints = demo_geo_points(identifiers)
        if self._provider is None:
            return self._fallback(
                waypoints,
                "AMap Web Service is not configured.",
            )
        if self._circuit_breaker is not None and not await self._circuit_breaker.allow_request():
            return self._fallback(
                waypoints,
                "AMap Web Service is temporarily unavailable.",
            )
        try:
            route = await self._provider.plan(
                waypoints[0],
                waypoints[-1],
                waypoints[1:-1],
            )
        except ProviderError:
            if self._circuit_breaker is not None:
                await self._circuit_breaker.record_failure()
            return self._fallback(
                waypoints,
                "AMap Web Service is temporarily unavailable.",
            )
        if self._circuit_breaker is not None:
            await self._circuit_breaker.record_success()
        return RealRoadRoute(
            provider="AMAP",
            source="AMAP_WEB_SERVICE",
            status="VERIFIED",
            coordinate_system="GCJ02",
            mapping_version=MAPPING_VERSION,
            distance_meters=route.distance_meters,
            duration_seconds=route.duration_seconds,
            waypoints=waypoints,
            polyline=route.polyline,
            fallback_reason=None,
        )

    @staticmethod
    def _fallback(waypoints, reason: str) -> RealRoadRoute:
        return RealRoadRoute(
            provider="AMAP",
            source="CLIENT_WAYPOINT_FALLBACK",
            status="CLIENT_MATCH_REQUIRED",
            coordinate_system="GCJ02",
            mapping_version=MAPPING_VERSION,
            distance_meters=None,
            duration_seconds=None,
            waypoints=waypoints,
            polyline=waypoints,
            fallback_reason=reason,
        )
