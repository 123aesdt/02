from typing import Protocol

from app.workspace_reads.models import (
    AnomalyListItem,
    DomainCounts,
    MyTaskPage,
    OrderListItem,
    Page,
    ReviewListItem,
    RuntimeThreadListItem,
    TeamTaskPage,
    VectorMemoryPage,
)


class WorkspaceReadRepository(Protocol):
    def list_orders(
        self,
        *,
        limit: int = 20,
        before_id: int | None,
        query: str | None,
        status: str | None,
    ) -> Page[OrderListItem]: ...

    def list_anomalies(
        self,
        *,
        limit: int = 20,
        before_id: int | None,
        query: str | None,
        risk: str | None,
        status: str | None,
    ) -> Page[AnomalyListItem]: ...

    def list_reviews(self, *, limit: int = 20, before_id: int | None) -> Page[ReviewListItem]: ...

    def list_my_tasks(
        self,
        *,
        subject_id: str,
        limit: int = 20,
        before_id: int | None,
        state: str | None,
    ) -> MyTaskPage: ...

    def list_team_tasks(
        self,
        *,
        assignee_subject_id: str | None,
        limit: int = 20,
        before_id: int | None,
        state: str | None,
    ) -> TeamTaskPage: ...

    def list_runtime_threads(
        self,
        *,
        limit: int = 20,
        before_id: int | None,
        status: str | None,
    ) -> Page[RuntimeThreadListItem]: ...

    def count_domains(self) -> DomainCounts: ...


class VectorMemoryReadRepository(Protocol):
    async def list_records(self, *, limit: int = 20, cursor: str | None = None) -> VectorMemoryPage: ...
