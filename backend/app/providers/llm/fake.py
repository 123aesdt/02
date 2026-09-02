from app.providers.errors import ProviderError, ProviderTimeout
from app.providers.llm.base import LLMResult


class FakeLLMProvider:
    def __init__(self, content: str = "", mode: str = "success") -> None:
        self._content, self._mode = content, mode

    async def generate(self, system_prompt: str, prompt: str, *, temperature: float = 0) -> LLMResult:
        if self._mode == "timeout":
            raise ProviderTimeout("LLM request timed out")
        if self._mode == "exception":
            raise ProviderError("LLM provider failed")
        return LLMResult(self._content, "fake-llm", "stop")
