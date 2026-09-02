"""Probe an OpenAI-compatible embedding response without exposing its vector or key."""

import asyncio
import json
import os

import httpx
from app.providers.embedding.openai_compatible import OpenAICompatibleEmbeddingProvider
from app.providers.errors import ProviderResponseError


async def main() -> None:
    observed_dimension: int | None = None

    async def observe(response: httpx.Response) -> None:
        nonlocal observed_dimension
        await response.aread()
        observed_dimension = len(response.json()["data"][0]["embedding"])

    async with httpx.AsyncClient(event_hooks={"response": [observe]}) as client:
        provider = OpenAICompatibleEmbeddingProvider(
            os.environ["EMBEDDING_BASE_URL"],
            os.environ["EMBEDDING_API_KEY"],
            os.environ["EMBEDDING_MODEL"],
            int(os.environ["EMBEDDING_DIMENSION"]),
            client=client,
        )
        try:
            await provider.embed_text("县域物流真实向量维度探测")
        except ProviderResponseError:
            if observed_dimension is None:
                raise
    print(json.dumps({"actual_dimension": observed_dimension}))


if __name__ == "__main__":
    asyncio.run(main())
