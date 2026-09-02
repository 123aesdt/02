from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class LLMResult:
    content: str
    model: str
    finish_reason: str | None
    usage: dict[str, int] | None = None


class LLMProvider(Protocol):
    async def generate(self, system_prompt: str, prompt: str, *, temperature: float = 0) -> LLMResult: ...
