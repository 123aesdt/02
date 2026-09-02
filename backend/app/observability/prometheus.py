"""One-second, fixed-catalog Prometheus query client."""

from dataclasses import dataclass

from httpx import AsyncClient

from app.observability.query_catalog import ObservabilityQueryKey, resolve_query


class PrometheusQueryError(Exception):
    pass


@dataclass(frozen=True)
class PrometheusSample:
    value: float
    timestamp: float
    labels: dict[str, str]


class PrometheusQueryClient:
    def __init__(self, base_url: str, *, timeout_seconds: float = 1.0, client: AsyncClient | None = None) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self._client = client

    async def instant(self, key: ObservabilityQueryKey, window: str) -> tuple[PrometheusSample, ...]:
        query = resolve_query(key, window)
        try:
            if self._client is None:
                async with AsyncClient(timeout=self._timeout) as client:
                    response = await client.get(f"{self._base_url}/api/v1/query", params={"query": query})
            else:
                response = await self._client.get(f"{self._base_url}/api/v1/query", params={"query": query}, timeout=self._timeout)
            response.raise_for_status()
            payload = response.json()
            result = payload["data"]["result"]
            return tuple(
                PrometheusSample(
                    float(item["value"][1]),
                    float(item["value"][0]),
                    {str(key): str(value) for key, value in item.get("metric", {}).items()},
                )
                for item in result
            )
        except Exception:
            raise PrometheusQueryError from None
