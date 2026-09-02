from typing import Protocol

from app.routing.models import RouteCandidate


class RouteProvider(Protocol):
    async def get_candidates(self) -> list[RouteCandidate]: ...

    def resolve_route_reference(self, reference: str) -> str | None: ...


class InMemoryRouteProvider:
    def __init__(self, candidates: list[RouteCandidate], references: dict[str, str]) -> None:
        self._candidates = candidates
        self._references = references

    @classmethod
    def default_catalog(cls) -> "InMemoryRouteProvider":
        return cls(
            [
                RouteCandidate("xinping-road", "新平路", 10.0, 20, "low", True, None, 0.0),
                RouteCandidate("national-102", "102国道", 13.0, 26, "low", True, None, 0.0),
                RouteCandidate("county-308", "308县道", 15.0, 30, "medium", True, None, 0.0),
            ],
            {"新平路": "xinping-road", "102国道": "national-102", "308县道": "county-308"},
        )

    async def get_candidates(self) -> list[RouteCandidate]:
        return list(self._candidates)

    def resolve_route_reference(self, reference: str) -> str | None:
        return next((route_id for name, route_id in self._references.items() if name in reference), None)
