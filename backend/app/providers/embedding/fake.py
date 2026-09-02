import hashlib


class FakeEmbeddingProvider:
    def __init__(self, dimension: int = 8) -> None:
        self.vector_dimension = dimension

    async def embed_text(self, text: str) -> list[float]:
        if not text.strip():
            raise ValueError("text must not be empty")
        vector = [0.0] * self.vector_dimension
        for character in text.lower():
            if character.isspace() or character in "：，。,.":
                continue
            digest = hashlib.sha256(character.encode()).digest()
            index = digest[0] % self.vector_dimension
            vector[index] += 1.0 if digest[1] % 2 else -1.0
        return vector
