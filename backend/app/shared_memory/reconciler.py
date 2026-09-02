from app.shared_memory.models import MemoryMutationResult
from app.shared_memory.service import SharedMemoryMutationService


class MemoryMutationReconciler:
    def __init__(self, service: SharedMemoryMutationService) -> None:
        self._service = service

    async def resume_mutation(self, mutation_id: str) -> MemoryMutationResult:
        return await self._service.resume_mutation(mutation_id)
