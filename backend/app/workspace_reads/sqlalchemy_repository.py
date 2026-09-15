from collections.abc import Callable

from sqlalchemy import case, func, or_, select
from sqlalchemy.orm import Session

from app.models.anomaly import Anomaly
from app.models.audit import AuditRecord
from app.models.demo_employee_account import DemoEmployeeAccount
from app.models.dispatch import Dispatch
from app.models.dispatch_publication import DispatchPublication
from app.models.order import Order
from app.models.runtime_thread import RuntimeThread
from app.models.task import DispatchTask
from app.workspace_reads.exceptions import TeamMemberNotFound
from app.workspace_reads.models import (
    AnomalyListItem,
    DomainCounts,
    MyTaskListItem,
    MyTaskPage,
    MyTaskSummary,
    OrderListItem,
    Page,
    ReviewListItem,
    RuntimeThreadListItem,
    TeamMemberTaskSummary,
    TeamTaskListItem,
    TeamTaskPage,
    TeamTaskSummary,
)

MY_TASK_STATUS_GROUPS = {
    "READY": ("APPROVED", "ASSIGNED"),
    "WAITING": ("PENDING", "QUEUED", "REVIEW_REQUIRED"),
    "ACTIVE": ("RUNNING", "PROCESSING", "IN_PROGRESS"),
    "ENDED": ("COMPLETED", "REJECTED", "FAILED", "CANCELLED"),
}


class SqlAlchemyWorkspaceReadRepository:
    def __init__(self, session_factory: Callable[[], Session]) -> None:
        self._session_factory = session_factory

    def list_orders(
        self,
        *,
        limit: int = 20,
        before_id: int | None,
        query: str | None,
        status: str | None,
    ) -> Page[OrderListItem]:
        limit = self._validated_limit(limit)
        conditions = self._order_conditions(query=query, status=status)
        anomaly_count = (
            select(func.count(Anomaly.id))
            .where(Anomaly.order_id == Order.id)
            .correlate(Order)
            .scalar_subquery()
        )
        latest_task_id = (
            select(DispatchTask.task_id)
            .where(DispatchTask.order_id == Order.id)
            .order_by(DispatchTask.id.desc())
            .limit(1)
            .correlate(Order)
            .scalar_subquery()
        )
        statement = select(
            Order.id,
            Order.order_no,
            Order.status,
            Order.driver_id,
            Order.vehicle_id,
            Order.route_id,
            Order.origin,
            Order.destination,
            Order.created_at,
            Order.updated_at,
            anomaly_count,
            latest_task_id,
        ).where(*conditions)
        if before_id is not None:
            statement = statement.where(Order.id < before_id)
        with self._session_factory() as session:
            rows = session.execute(statement.order_by(Order.id.desc()).limit(limit + 1)).all()
            total = session.scalar(select(func.count()).select_from(Order).where(*conditions)) or 0
            demo_count = session.scalar(
                select(func.count())
                .select_from(Order)
                .where(*conditions, Order.order_no.like("DEMO-ORDER-%"))
            ) or 0
        visible = rows[:limit]
        return Page(
            items=tuple(OrderListItem(*row) for row in visible),
            total=total,
            next_cursor=str(visible[-1].id) if len(rows) > limit else None,
            provenance=self._provenance(total=total, demo_count=demo_count),
        )

    def list_anomalies(
        self,
        *,
        limit: int = 20,
        before_id: int | None,
        query: str | None,
        risk: str | None,
        status: str | None,
    ) -> Page[AnomalyListItem]:
        limit = self._validated_limit(limit)
        conditions = self._anomaly_conditions(query=query, risk=risk, status=status)
        latest_task_id = (
            select(DispatchTask.task_id)
            .where(DispatchTask.anomaly_id == Anomaly.id)
            .order_by(DispatchTask.id.desc())
            .limit(1)
            .correlate(Anomaly)
            .scalar_subquery()
        )
        statement = (
            select(
                Anomaly.id,
                Anomaly.anomaly_no,
                Order.order_no,
                Order.driver_id,
                Order.vehicle_id,
                Order.route_id,
                latest_task_id,
                Anomaly.anomaly_type,
                Anomaly.severity,
                Anomaly.description,
                Anomaly.status,
                Anomaly.reported_at,
            )
            .select_from(Anomaly)
            .outerjoin(Order, Order.id == Anomaly.order_id)
            .where(*conditions)
        )
        if before_id is not None:
            statement = statement.where(Anomaly.id < before_id)
        with self._session_factory() as session:
            rows = session.execute(statement.order_by(Anomaly.id.desc()).limit(limit + 1)).all()
            total = session.scalar(
                select(func.count()).select_from(Anomaly).outerjoin(Order, Order.id == Anomaly.order_id).where(*conditions)
            ) or 0
            demo_count = session.scalar(
                select(func.count())
                .select_from(Anomaly)
                .outerjoin(Order, Order.id == Anomaly.order_id)
                .where(*conditions, Anomaly.anomaly_no.like("DEMO-ANOM-%"))
            ) or 0
        visible = rows[:limit]
        return Page(
            items=tuple(AnomalyListItem(*row) for row in visible),
            total=total,
            next_cursor=str(visible[-1].id) if len(rows) > limit else None,
            provenance=self._provenance(total=total, demo_count=demo_count),
        )

    def list_reviews(self, *, limit: int = 20, before_id: int | None) -> Page[ReviewListItem]:
        limit = self._validated_limit(limit)
        conditions = [DispatchTask.status == "REVIEW_REQUIRED"]
        latest_dispatch_id = (
            select(func.max(Dispatch.id))
            .where(Dispatch.task_id == DispatchTask.id)
            .correlate(DispatchTask)
            .scalar_subquery()
        )
        latest_audit_id = (
            select(func.max(AuditRecord.id))
            .where(
                AuditRecord.task_id == DispatchTask.id,
                AuditRecord.dispatch_id == latest_dispatch_id,
            )
            .correlate(DispatchTask)
            .scalar_subquery()
        )
        statement = (
            select(
                DispatchTask.id,
                DispatchTask.task_id,
                Order.order_no,
                Anomaly.severity,
                Dispatch.decision_reason,
                Order.vehicle_id,
                Dispatch.original_route_id,
                Dispatch.target_route_id,
                DispatchTask.status,
                DispatchTask.created_at,
                Dispatch.decision_reason,
                Dispatch.recommended_action,
                Dispatch.analysis_mode,
                Dispatch.issue_subtype,
            )
            .select_from(DispatchTask)
            .outerjoin(Order, Order.id == DispatchTask.order_id)
            .outerjoin(Anomaly, Anomaly.id == DispatchTask.anomaly_id)
            .outerjoin(Dispatch, Dispatch.id == latest_dispatch_id)
            .outerjoin(AuditRecord, AuditRecord.id == latest_audit_id)
            .where(*conditions)
        )
        if before_id is not None:
            statement = statement.where(DispatchTask.id < before_id)
        with self._session_factory() as session:
            rows = session.execute(statement.order_by(DispatchTask.id.desc()).limit(limit + 1)).all()
            total = session.scalar(select(func.count()).select_from(DispatchTask).where(*conditions)) or 0
            demo_count = session.scalar(
                select(func.count())
                .select_from(DispatchTask)
                .where(*conditions, DispatchTask.task_id.like("DEMO-TASK-%"))
            ) or 0
        visible = rows[:limit]
        return Page(
            items=tuple(ReviewListItem(*row) for row in visible),
            total=total,
            next_cursor=str(visible[-1].id) if len(rows) > limit else None,
            provenance=self._provenance(total=total, demo_count=demo_count),
        )

    def list_my_tasks(
        self,
        *,
        subject_id: str,
        limit: int = 20,
        before_id: int | None,
        state: str | None,
    ) -> MyTaskPage:
        limit = self._validated_limit(limit)
        owner_condition = DispatchTask.assignee_subject_id == subject_id
        conditions = [owner_condition]
        if state is not None:
            statuses = MY_TASK_STATUS_GROUPS.get(state)
            if statuses is None:
                raise ValueError("unsupported my-task state")
            conditions.append(DispatchTask.status.in_(statuses))
        latest_dispatch_id = (
            select(func.max(Dispatch.id))
            .where(Dispatch.task_id == DispatchTask.id)
            .correlate(DispatchTask)
            .scalar_subquery()
        )
        statement = (
            select(
                DispatchTask.id,
                DispatchTask.task_id,
                Order.order_no,
                Anomaly.severity,
                Anomaly.description,
                Order.vehicle_id,
                Dispatch.original_route_id,
                DispatchPublication.route_id,
                DispatchTask.status,
                DispatchTask.created_at,
                DispatchTask.updated_at,
                Order.origin,
                Order.destination,
                case((DispatchPublication.id.is_not(None), "PUBLISHED"), else_="PENDING"),
                DispatchPublication.published_at,
                DispatchPublication.route_instruction,
                case((DispatchTask.anomaly_id.is_(None), True), else_=False),
            )
            .select_from(DispatchTask)
            .outerjoin(Order, Order.id == DispatchTask.order_id)
            .outerjoin(Anomaly, Anomaly.id == DispatchTask.anomaly_id)
            .outerjoin(Dispatch, Dispatch.id == latest_dispatch_id)
            .outerjoin(
                DispatchPublication,
                (DispatchPublication.task_id == DispatchTask.id)
                & (DispatchPublication.dispatch_id == Dispatch.id),
            )
            .where(*conditions)
        )
        if before_id is not None:
            statement = statement.where(DispatchTask.id < before_id)
        summary_statement = select(
            func.count(DispatchTask.id),
            func.sum(case((DispatchTask.status.in_(MY_TASK_STATUS_GROUPS["READY"]), 1), else_=0)),
            func.sum(case((DispatchTask.status.in_(MY_TASK_STATUS_GROUPS["WAITING"]), 1), else_=0)),
            func.sum(case((DispatchTask.status.in_(MY_TASK_STATUS_GROUPS["ACTIVE"]), 1), else_=0)),
            func.sum(case((DispatchTask.status.in_(MY_TASK_STATUS_GROUPS["ENDED"]), 1), else_=0)),
        ).where(owner_condition)
        with self._session_factory() as session:
            rows = session.execute(statement.order_by(DispatchTask.id.desc()).limit(limit + 1)).all()
            total = session.scalar(select(func.count()).select_from(DispatchTask).where(*conditions)) or 0
            demo_count = session.scalar(
                select(func.count())
                .select_from(DispatchTask)
                .where(*conditions, DispatchTask.task_id.like("DEMO-TASK-%"))
            ) or 0
            summary_row = session.execute(summary_statement).one()
        visible = rows[:limit]
        return MyTaskPage(
            items=tuple(MyTaskListItem(*row) for row in visible),
            summary=MyTaskSummary(
                total=int(summary_row[0] or 0),
                ready=int(summary_row[1] or 0),
                waiting=int(summary_row[2] or 0),
                active=int(summary_row[3] or 0),
                ended=int(summary_row[4] or 0),
            ),
            total=total,
            next_cursor=str(visible[-1].id) if len(rows) > limit else None,
            provenance=self._provenance(total=total, demo_count=demo_count),
        )

    def list_team_tasks(
        self,
        *,
        assignee_subject_id: str | None,
        limit: int = 20,
        before_id: int | None,
        state: str | None,
    ) -> TeamTaskPage:
        limit = self._validated_limit(limit)
        member_statement = (
            select(
                DemoEmployeeAccount.employee_id,
                DemoEmployeeAccount.display_name,
            )
            .where(
                DemoEmployeeAccount.is_active.is_(True),
                DemoEmployeeAccount.role == "EMPLOYEE",
            )
            .order_by(DemoEmployeeAccount.employee_id)
        )
        with self._session_factory() as session:
            member_rows = session.execute(member_statement).all()
            member_ids = tuple(row.employee_id for row in member_rows)
            if assignee_subject_id is not None and assignee_subject_id not in member_ids:
                raise TeamMemberNotFound(assignee_subject_id)
            if not member_ids:
                return TeamTaskPage(
                    items=(),
                    summary=TeamTaskSummary(total=0, ready=0, waiting=0, active=0, ended=0),
                    members=(),
                    total=0,
                    next_cursor=None,
                )

            base_condition = DispatchTask.assignee_subject_id.in_(member_ids)
            conditions = [base_condition]
            if assignee_subject_id is not None:
                conditions.append(DispatchTask.assignee_subject_id == assignee_subject_id)
            if state is not None:
                statuses = MY_TASK_STATUS_GROUPS.get(state)
                if statuses is None:
                    raise ValueError("unsupported team-task state")
                conditions.append(DispatchTask.status.in_(statuses))

            latest_dispatch_id = (
                select(func.max(Dispatch.id))
                .where(Dispatch.task_id == DispatchTask.id)
                .correlate(DispatchTask)
                .scalar_subquery()
            )
            statement = (
                select(
                    DispatchTask.id,
                    DispatchTask.task_id,
                    DispatchTask.assignee_subject_id,
                    DemoEmployeeAccount.display_name,
                    Order.order_no,
                    Anomaly.severity,
                    Anomaly.description,
                    Order.vehicle_id,
                    Dispatch.original_route_id,
                    Dispatch.target_route_id,
                    DispatchTask.status,
                    DispatchTask.created_at,
                    DispatchTask.updated_at,
                )
                .select_from(DispatchTask)
                .join(
                    DemoEmployeeAccount,
                    DemoEmployeeAccount.employee_id == DispatchTask.assignee_subject_id,
                )
                .outerjoin(Order, Order.id == DispatchTask.order_id)
                .outerjoin(Anomaly, Anomaly.id == DispatchTask.anomaly_id)
                .outerjoin(Dispatch, Dispatch.id == latest_dispatch_id)
                .where(*conditions)
            )
            if before_id is not None:
                statement = statement.where(DispatchTask.id < before_id)

            summary_statement = select(
                func.count(DispatchTask.id),
                func.sum(case((DispatchTask.status.in_(MY_TASK_STATUS_GROUPS["READY"]), 1), else_=0)),
                func.sum(case((DispatchTask.status.in_(MY_TASK_STATUS_GROUPS["WAITING"]), 1), else_=0)),
                func.sum(case((DispatchTask.status.in_(MY_TASK_STATUS_GROUPS["ACTIVE"]), 1), else_=0)),
                func.sum(case((DispatchTask.status.in_(MY_TASK_STATUS_GROUPS["ENDED"]), 1), else_=0)),
            ).where(base_condition)
            member_summary_statement = (
                select(
                    DemoEmployeeAccount.employee_id,
                    DemoEmployeeAccount.display_name,
                    func.count(DispatchTask.id),
                    func.sum(
                        case((DispatchTask.status.in_(MY_TASK_STATUS_GROUPS["READY"]), 1), else_=0)
                    ),
                    func.sum(
                        case((DispatchTask.status.in_(MY_TASK_STATUS_GROUPS["WAITING"]), 1), else_=0)
                    ),
                    func.sum(
                        case((DispatchTask.status.in_(MY_TASK_STATUS_GROUPS["ACTIVE"]), 1), else_=0)
                    ),
                    func.sum(
                        case((DispatchTask.status.in_(MY_TASK_STATUS_GROUPS["ENDED"]), 1), else_=0)
                    ),
                )
                .select_from(DemoEmployeeAccount)
                .outerjoin(
                    DispatchTask,
                    DispatchTask.assignee_subject_id == DemoEmployeeAccount.employee_id,
                )
                .where(
                    DemoEmployeeAccount.is_active.is_(True),
                    DemoEmployeeAccount.role == "EMPLOYEE",
                )
                .group_by(
                    DemoEmployeeAccount.employee_id,
                    DemoEmployeeAccount.display_name,
                )
                .order_by(DemoEmployeeAccount.employee_id)
            )

            rows = session.execute(statement.order_by(DispatchTask.id.desc()).limit(limit + 1)).all()
            total = session.scalar(
                select(func.count()).select_from(DispatchTask).where(*conditions)
            ) or 0
            demo_count = session.scalar(
                select(func.count())
                .select_from(DispatchTask)
                .where(*conditions, DispatchTask.task_id.like("DEMO-TASK-%"))
            ) or 0
            summary_row = session.execute(summary_statement).one()
            member_summary_rows = session.execute(member_summary_statement).all()

        visible = rows[:limit]
        return TeamTaskPage(
            items=tuple(TeamTaskListItem(*row) for row in visible),
            summary=TeamTaskSummary(
                total=int(summary_row[0] or 0),
                ready=int(summary_row[1] or 0),
                waiting=int(summary_row[2] or 0),
                active=int(summary_row[3] or 0),
                ended=int(summary_row[4] or 0),
            ),
            members=tuple(
                TeamMemberTaskSummary(
                    subject_id=row[0],
                    display_name=row[1],
                    total=int(row[2] or 0),
                    ready=int(row[3] or 0),
                    waiting=int(row[4] or 0),
                    active=int(row[5] or 0),
                    ended=int(row[6] or 0),
                )
                for row in member_summary_rows
            ),
            total=total,
            next_cursor=str(visible[-1].id) if len(rows) > limit else None,
            provenance=self._provenance(total=total, demo_count=demo_count),
        )

    def list_runtime_threads(
        self,
        *,
        limit: int = 20,
        before_id: int | None,
        status: str | None,
    ) -> Page[RuntimeThreadListItem]:
        limit = self._validated_limit(limit)
        conditions = [RuntimeThread.status == status] if status is not None else []
        statement = select(
            RuntimeThread.id,
            RuntimeThread.thread_id,
            RuntimeThread.task_id,
            RuntimeThread.status,
            RuntimeThread.current_node,
            RuntimeThread.next_node,
            RuntimeThread.state_version,
            RuntimeThread.checkpoint_count,
            RuntimeThread.worker_consumer,
            RuntimeThread.terminal_at,
            RuntimeThread.updated_at,
        ).where(*conditions)
        if before_id is not None:
            statement = statement.where(RuntimeThread.id < before_id)
        with self._session_factory() as session:
            rows = session.execute(statement.order_by(RuntimeThread.id.desc()).limit(limit + 1)).all()
            total = session.scalar(select(func.count()).select_from(RuntimeThread).where(*conditions)) or 0
            demo_count = session.scalar(
                select(func.count())
                .select_from(RuntimeThread)
                .where(*conditions, RuntimeThread.thread_id.like("demo-thread-%"))
            ) or 0
        visible = rows[:limit]
        return Page(
            items=tuple(RuntimeThreadListItem(*row) for row in visible),
            total=total,
            next_cursor=str(visible[-1].id) if len(rows) > limit else None,
            provenance=self._provenance(total=total, demo_count=demo_count),
        )

    def count_domains(self) -> DomainCounts:
        with self._session_factory() as session:
            orders = session.scalar(select(func.count()).select_from(Order)) or 0
            anomalies = session.scalar(select(func.count()).select_from(Anomaly)) or 0
            reviews = session.scalar(
                select(func.count()).select_from(DispatchTask).where(DispatchTask.status == "REVIEW_REQUIRED")
            ) or 0
            runtime_threads = session.scalar(select(func.count()).select_from(RuntimeThread)) or 0
            demo_records = (
                (session.scalar(select(func.count()).select_from(Order).where(Order.order_no.like("DEMO-ORDER-%"))) or 0)
                + (
                    session.scalar(
                        select(func.count()).select_from(Anomaly).where(Anomaly.anomaly_no.like("DEMO-ANOM-%"))
                    )
                    or 0
                )
                + (
                    session.scalar(
                        select(func.count())
                        .select_from(DispatchTask)
                        .where(
                            DispatchTask.status == "REVIEW_REQUIRED",
                            DispatchTask.task_id.like("DEMO-TASK-%"),
                        )
                    )
                    or 0
                )
                + (
                    session.scalar(
                        select(func.count())
                        .select_from(RuntimeThread)
                        .where(RuntimeThread.thread_id.like("demo-thread-%"))
                    )
                    or 0
                )
            )
            total_records = orders + anomalies + reviews + runtime_threads
            return DomainCounts(
                orders=orders,
                anomalies=anomalies,
                reviews=reviews,
                runtime_threads=runtime_threads,
                provenance=self._provenance(total=total_records, demo_count=demo_records),
            )

    @staticmethod
    def _provenance(*, total: int, demo_count: int) -> str:
        if total > 0 and demo_count == total:
            return "DEMO"
        if demo_count > 0:
            return "MIXED"
        return "LIVE"

    @staticmethod
    def _order_conditions(*, query: str | None, status: str | None) -> list[object]:
        conditions: list[object] = []
        if query:
            pattern = f"%{query}%"
            conditions.append(
                or_(
                    Order.order_no.ilike(pattern),
                    Order.driver_id.ilike(pattern),
                    Order.vehicle_id.ilike(pattern),
                    Order.route_id.ilike(pattern),
                    Order.origin.ilike(pattern),
                    Order.destination.ilike(pattern),
                )
            )
        if status is not None:
            conditions.append(Order.status == status)
        return conditions

    @staticmethod
    def _anomaly_conditions(*, query: str | None, risk: str | None, status: str | None) -> list[object]:
        conditions: list[object] = []
        if query:
            pattern = f"%{query}%"
            conditions.append(
                or_(
                    Anomaly.anomaly_no.ilike(pattern),
                    Order.order_no.ilike(pattern),
                    Anomaly.anomaly_type.ilike(pattern),
                    Anomaly.description.ilike(pattern),
                )
            )
        if risk is not None:
            conditions.append(Anomaly.severity == risk)
        if status is not None:
            conditions.append(Anomaly.status == status)
        return conditions

    @staticmethod
    def _validated_limit(limit: int) -> int:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be between 1 and 100")
        return limit
