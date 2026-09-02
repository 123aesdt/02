import json

import pytest
from httpx import AsyncClient, MockTransport, Response

from app.providers.embedding.fake import FakeEmbeddingProvider
from app.providers.embedding.openai_compatible import OpenAICompatibleEmbeddingProvider
from app.providers.errors import ProviderResponseError, ProviderTimeout
from app.providers.llm.fake import FakeLLMProvider
from app.providers.llm.openai_compatible import OpenAICompatibleLLMProvider


@pytest.mark.asyncio
async def test_llm_provider_contract_and_fake_success():
    result = await FakeLLMProvider(content="safe plan").generate("system", "prompt")
    assert (result.content, result.model, result.finish_reason) == ("safe plan", "fake-llm", "stop")


@pytest.mark.asyncio
async def test_embedding_provider_contract_is_deterministic():
    provider = FakeEmbeddingProvider(dimension=8)
    assert await provider.embed_text("rainy xinping road") == await provider.embed_text("rainy xinping road")
    assert len(await provider.embed_text("rainy xinping road")) == 8


@pytest.mark.asyncio
async def test_openai_compatible_llm_request_mapping():
    async def handler(request):
        assert request.headers["authorization"] == "Bearer secret"
        assert request.url.path.endswith("/chat/completions")
        assert json.loads(request.content)["model"] == "llm-model"
        return Response(200, json={"model": "llm-model", "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}]})

    provider = OpenAICompatibleLLMProvider("https://model.test/v1", "secret", "llm-model", client=AsyncClient(transport=MockTransport(handler)))
    assert (await provider.generate("sys", "hello")).content == "ok"


@pytest.mark.asyncio
async def test_openai_compatible_embedding_request_mapping_and_errors():
    async def handler(request):
        if "/bad/" in request.url.path:
            return Response(500, json={"error": "bad"})
        assert json.loads(request.content)["model"] == "embed-model"
        return Response(200, json={"data": [{"embedding": [0.1, 0.2, 0.3]}]})

    client = AsyncClient(transport=MockTransport(handler))
    provider = OpenAICompatibleEmbeddingProvider("https://embed.test/v1", "secret", "embed-model", 3, client=client)
    assert await provider.embed_text("hello") == [0.1, 0.2, 0.3]
    bad = OpenAICompatibleEmbeddingProvider("https://embed.test/bad", "secret", "embed-model", 3, client=client)
    with pytest.raises(ProviderResponseError):
        await bad.embed_text("hello")


@pytest.mark.asyncio
async def test_provider_timeout_and_secret_safety():
    provider = FakeLLMProvider(mode="timeout")
    with pytest.raises(ProviderTimeout):
        await provider.generate("s", "p")
    real = OpenAICompatibleLLMProvider("https://model.test", "secret-value", "model")
    assert "secret-value" not in repr(real)
