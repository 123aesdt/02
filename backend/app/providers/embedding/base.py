from typing import Protocol


class EmbeddingProvider(Protocol):
    vector_dimension: int

    async def embed_text(self, text: str) -> list[float]: ...
