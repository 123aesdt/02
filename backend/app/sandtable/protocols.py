from typing import Protocol

from app.sandtable.models import SandtableTaskContext


class SandtableContextProvider(Protocol):
    def load(self, order_id: int) -> SandtableTaskContext: ...

    def set_edge_status(self, edge_id: str, status: str) -> int: ...
