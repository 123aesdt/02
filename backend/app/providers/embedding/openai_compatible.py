import httpx

from app.providers.errors import ProviderResponseError, ProviderTimeout


class OpenAICompatibleEmbeddingProvider:
    def __init__(self, base_url: str, api_key: str, model: str, dimension: int, *, client: httpx.AsyncClient | None = None, timeout: float = 10) -> None:
        self._base_url, self._api_key, self._model, self.vector_dimension, self._client, self._timeout = (
            base_url.rstrip("/"),
            api_key,
            model,
            dimension,
            client,
            timeout,
        )

    async def embed_text(self, text: str) -> list[float]:
        try:
            client = self._client or httpx.AsyncClient(timeout=self._timeout)
            response = await client.post(
                f"{self._base_url}/embeddings", headers={"Authorization": f"Bearer {self._api_key}"}, json={"model": self._model, "input": text}
            )
            response.raise_for_status()
            vector = response.json()["data"][0]["embedding"]
            if len(vector) != self.vector_dimension:
                raise ValueError("dimension mismatch")
            return vector
        except httpx.TimeoutException as error:
            raise ProviderTimeout("Embedding request timed out") from error
        except (httpx.HTTPError, KeyError, ValueError, IndexError, TypeError) as error:
            raise ProviderResponseError("Embedding provider response invalid") from error
