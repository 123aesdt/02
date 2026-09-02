import httpx

from app.providers.errors import ProviderResponseError, ProviderTimeout
from app.providers.llm.base import LLMResult


class OpenAICompatibleLLMProvider:
    def __init__(self, base_url: str, api_key: str, model: str, *, client: httpx.AsyncClient | None = None, timeout: float = 10) -> None:
        self._base_url, self._api_key, self._model, self._client, self._timeout = base_url.rstrip("/"), api_key, model, client, timeout

    async def generate(self, system_prompt: str, prompt: str, *, temperature: float = 0) -> LLMResult:
        try:
            client = self._client or httpx.AsyncClient(timeout=self._timeout)
            response = await client.post(
                f"{self._base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={
                    "model": self._model,
                    "messages": [{"role": "system", "content": system_prompt}, {"role": "user", "content": prompt}],
                    "temperature": temperature,
                },
            )
            response.raise_for_status()
            payload = response.json()
            choice = payload["choices"][0]
            return LLMResult(choice["message"]["content"], payload.get("model", self._model), choice.get("finish_reason"), payload.get("usage"))
        except httpx.TimeoutException as error:
            raise ProviderTimeout("LLM request timed out") from error
        except (httpx.HTTPError, KeyError, ValueError, IndexError, TypeError) as error:
            raise ProviderResponseError("LLM provider response invalid") from error
