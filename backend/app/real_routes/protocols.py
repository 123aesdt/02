from typing import Protocol

from app.real_routes.models import DrivingRouteResult, GeoPoint


class DrivingRouteProvider(Protocol):
    async def plan(
        self,
        origin: GeoPoint,
        destination: GeoPoint,
        waypoints: tuple[GeoPoint, ...],
    ) -> DrivingRouteResult: ...
