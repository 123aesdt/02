from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, TypeVar

from sqlalchemy.exc import DisconnectionError, InterfaceError, OperationalError

from app.workspace_reads.models import (
    AnomalyListItem,
    MyTaskPage,
    OrderListItem,
    Page,
    ReviewListItem,
    RuntimeThreadListItem,
    TeamTaskPage,
    VectorMemoryPage,
)
from app.workspace_reads.protocols import VectorMemoryReadRepository, WorkspaceReadRepository
from app.workspace_reads.qdrant_repository import (
    InvalidVectorMemoryCursor as AdapterInvalidVectorMemoryCursor,
)
from app.workspace_reads.qdrant_repository import (
    VectorMemoryReadUnavailable as AdapterVectorMemoryReadUnavailable,
)


class InvalidWorkspaceCursor(ValueError):
    pass


class WorkspaceReadUnavailable(RuntimeError):
    pass


class InvalidVectorMemoryCursor(ValueError):
    pass


class VectorMemoryReadUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class WorkspaceOverview:
    orders: int
    anomalies: int
    reviews: int
    runtime_threads: int
    provenance: Literal["LIVE", "DEMO", "MIXED"]


def parse_numeric_cursor(cursor: str | None) -> int | None:
    if cursor is None:
        return None
    if (
        not isinstance(cursor, str)
        or not cursor.isascii()
        or not cursor.isdecimal()
        or len(cursor) > 19
    ):
        raise InvalidWorkspaceCursor("workspace cursor must be a numeric string")
    value = int(cursor)
    if value > 9_223_372_036_854_775_807:
        raise InvalidWorkspaceCursor("workspace cursor is outside the supported range")
    return value


T = TypeVar("T")


class WorkspaceReadService:
    def __init__(self, mysql: WorkspaceReadRepository, vectors: VectorMemoryReadRepository) -> None:
        self._mysql = mysql
        self._vectors = vectors

    def get_overview(self) -> WorkspaceOverview:
        counts = self._mysql_read(self._mysql.count_domains)
        return WorkspaceOverview(
            orders=counts.orders,
            anomalies=counts.anomalies,
            reviews=counts.reviews,
            runtime_threads=counts.runtime_threads,
            provenance=counts.provenance,
        )

    def list_orders(
        self, *, limit: int, cursor: str | None, query: str | None, status: str | None
    ) -> Page[OrderListItem]:
        before_id = parse_numeric_cursor(cursor)
        return self._mysql_read(
            lambda: self._mysql.list_orders(limit=limit, before_id=before_id, query=query, status=status)
        )

    def list_anomalies(
        self, *, limit: int, cursor: str | None, query: str | None, risk: str | None, status: str | None
    ) -> Page[AnomalyListItem]:
        before_id = parse_numeric_cursor(cursor)
        return self._mysql_read(
            lambda: self._mysql.list_anomalies(
                limit=limit, before_id=before_id, query=query, risk=risk, status=status
            )
        )

    def list_reviews(self, *, limit: int, cursor: str | None) -> Page[ReviewListItem]:
        before_id = parse_numeric_cursor(cursor)
        return self._mysql_read(lambda: self._mysql.list_reviews(limit=limit, before_id=before_id))

    def list_my_tasks(
        self,
        *,
        subject_id: str,
        limit: int,
        cursor: str | None,
        state: str | None,
    ) -> MyTaskPage:
        before_id = parse_numeric_cursor(cursor)
        return self._mysql_read(
            lambda: self._mysql.list_my_tasks(
                subject_id=subject_id,
                limit=limit,
                before_id=before_id,
                state=state,
            )
        )

    def list_team_tasks(
        self,
        *,
        assignee_subject_id: str | None,
        limit: int,
        cursor: str | None,
        state: str | None,
    ) -> TeamTaskPage:
        before_id = parse_numeric_cursor(cursor)
        return self._mysql_read(
            lambda: self._mysql.list_team_tasks(
                assignee_subject_id=assignee_subject_id,
                limit=limit,
                before_id=before_id,
                state=state,
            )
        )

    def list_runtime_threads(
        self, *, limit: int, cursor: str | None, status: str | None
    ) -> Page[RuntimeThreadListItem]:
        before_id = parse_numeric_cursor(cursor)
        return self._mysql_read(
            lambda: self._mysql.list_runtime_threads(limit=limit, before_id=before_id, status=status)
        )

    async def list_vector_memories(self, *, limit: int, cursor: str | None) -> VectorMemoryPage:
        try:
            return await self._vectors.list_records(limit=limit, cursor=cursor)
        except AdapterInvalidVectorMemoryCursor:
            raise InvalidVectorMemoryCursor("invalid vector memory cursor") from None
        except AdapterVectorMemoryReadUnavailable:
            raise VectorMemoryReadUnavailable("vector memory read unavailable") from None

    @staticmethod
    def _mysql_read(operation: Callable[[], T]) -> T:
        try:
            return operation()
        except (DisconnectionError, InterfaceError, OperationalError) as error:
            if WorkspaceReadService._is_connection_failure(error):
                raise WorkspaceReadUnavailable("workspace read unavailable") from None
            raise

    @staticmethod
    def _is_connection_failure(error: BaseException) -> bool:
        if (
            isinstance(error, DisconnectionError)
            or bool(getattr(error, "connection_invalidated", False))
            or isinstance(getattr(error, "orig", None), ConnectionError)
        ):
            return True

        original = getattr(error, "orig", None)
        arguments = getattr(original, "args", ())
        mysql_code = arguments[0] if arguments else None
        if mysql_code in {2002, 2003, 2006, 2013}:
            return True

        sqlstate = getattr(original, "sqlstate", None) or getattr(original, "sql_state", None)
        if sqlstate is None and isinstance(mysql_code, str):
            sqlstate = mysql_code
        return isinstance(sqlstate, str) and sqlstate.upper().startswith("08")
