from datetime import datetime

import pytest

from app.models.anomaly import Anomaly
from app.models.audit import AuditRecord
from app.models.demo_employee_account import DemoEmployeeAccount
from app.models.dispatch import Dispatch
from app.models.dispatch_publication import DispatchPublication
from app.models.order import Order
from app.models.runtime_thread import RuntimeThread
from app.models.task import DispatchTask

REVIEW_TIME = datetime(2026, 8, 29, 10, 30, 0)


def seed_workspace(factory) -> None:
    with factory() as session:
        order_one = Order(
            id=1,
            order_no="DEMO-ORDER-001",
            status="IN_TRANSIT",
            driver_id="driver-1",
            vehicle_id="苏G·N2147",
            route_id="西河乡道",
            origin="青云镇",
            destination="临港镇",
            created_at=datetime(2026, 8, 29, 8, 0, 0),
            updated_at=datetime(2026, 8, 29, 8, 0, 0),
        )
        order_two = Order(
            id=2,
            order_no="DEMO-ORDER-002",
            status="DELAYED",
            driver_id="driver-2",
            vehicle_id="苏G·N2148",
            route_id="东河乡道",
            origin="东河镇",
            destination="县城分拨中心",
            created_at=REVIEW_TIME,
            updated_at=REVIEW_TIME,
        )
        order_three = Order(
            id=3,
            order_no="LIVE-ORDER-003",
            status="PENDING",
            driver_id=None,
            vehicle_id=None,
            route_id=None,
            origin="北山镇",
            destination="南门镇",
            created_at=datetime(2026, 8, 29, 11, 0, 0),
            updated_at=datetime(2026, 8, 29, 11, 0, 0),
        )
        anomaly_one = Anomaly(
            id=1,
            anomaly_no="LIVE-ANOM-001",
            order_id=1,
            anomaly_type="WEATHER",
            severity="LOW",
            description="降雨",
            status="RESOLVED",
            reported_at=datetime(2026, 8, 29, 8, 5, 0),
            created_at=datetime(2026, 8, 29, 8, 5, 0),
            updated_at=datetime(2026, 8, 29, 8, 5, 0),
        )
        anomaly_two = Anomaly(
            id=2,
            anomaly_no="DEMO-ANOM-002",
            order_id=2,
            anomaly_type="ROAD",
            severity="HIGH",
            description="道路封闭",
            status="OPEN",
            reported_at=REVIEW_TIME,
            created_at=REVIEW_TIME,
            updated_at=REVIEW_TIME,
        )
        task_approved = DispatchTask(
            id=1,
            task_id="TASK-approved-1",
            order_id=1,
            anomaly_id=1,
            status="APPROVED",
            idempotency_key="approved-1",
            assignee_subject_id="dispatcher-1",
            created_at=datetime(2026, 8, 29, 8, 10, 0),
            updated_at=datetime(2026, 8, 29, 8, 10, 0),
        )
        task_review = DispatchTask(
            id=2,
            task_id="TASK-review-2",
            order_id=2,
            anomaly_id=2,
            status="REVIEW_REQUIRED",
            idempotency_key="review-2",
            assignee_subject_id="dispatcher-1",
            created_at=REVIEW_TIME,
            updated_at=REVIEW_TIME,
        )
        task_latest = DispatchTask(
            id=3,
            task_id="TASK-latest-3",
            order_id=2,
            anomaly_id=2,
            status="APPROVED",
            idempotency_key="latest-3",
            assignee_subject_id="dispatcher-2",
            created_at=datetime(2026, 8, 29, 10, 35, 0),
            updated_at=datetime(2026, 8, 29, 10, 35, 0),
        )
        task_operator = DispatchTask(
            id=4,
            task_id="TASK-operator-4",
            order_id=3,
            anomaly_id=None,
            status="RUNNING",
            idempotency_key="operator-4",
            assignee_subject_id="operator-1",
            created_at=datetime(2026, 8, 29, 11, 5, 0),
            updated_at=datetime(2026, 8, 29, 11, 5, 0),
        )
        task_inactive_dispatcher = DispatchTask(
            id=5,
            task_id="TASK-inactive-5",
            order_id=3,
            anomaly_id=None,
            status="COMPLETED",
            idempotency_key="inactive-5",
            assignee_subject_id="dispatcher-inactive",
            created_at=datetime(2026, 8, 29, 11, 10, 0),
            updated_at=datetime(2026, 8, 29, 11, 10, 0),
        )
        dispatcher_one = DemoEmployeeAccount(
            employee_id="dispatcher-1",
            display_name="调度员一号",
            role="EMPLOYEE",
            is_active=True,
        )
        dispatcher_two = DemoEmployeeAccount(
            employee_id="dispatcher-2",
            display_name="调度员二号",
            role="EMPLOYEE",
            is_active=True,
        )
        operator = DemoEmployeeAccount(
            employee_id="operator-1",
            display_name="运营员一号",
            role="OPERATOR",
            is_active=True,
        )
        inactive_dispatcher = DemoEmployeeAccount(
            employee_id="dispatcher-inactive",
            display_name="停用调度员",
            role="EMPLOYEE",
            is_active=False,
        )
        dispatch_approved = Dispatch(
            id=1,
            dispatch_no="DISPATCH-001",
            order_id=1,
            task_id=1,
            original_route_id="西河乡道",
            target_route_id="西河乡道-绕行",
            decision_reason="天气绕行",
            status="APPROVED",
            created_at=datetime(2026, 8, 29, 8, 15, 0),
            updated_at=datetime(2026, 8, 29, 8, 15, 0),
        )
        dispatch_review = Dispatch(
            id=2,
            dispatch_no="DISPATCH-002",
            order_id=2,
            task_id=2,
            original_route_id="东河乡道",
            target_route_id=None,
            decision_reason="道路封闭",
            recommended_action="停在安全位置并等待调度配置替代路线。",
            analysis_mode="EIGHT_AGENT_RULE_ASSISTED",
            issue_subtype="CLOSURE",
            status="PENDING_REVIEW",
            created_at=REVIEW_TIME,
            updated_at=REVIEW_TIME,
        )
        audit_approved = AuditRecord(
            id=1,
            task_id=1,
            dispatch_id=1,
            result="APPROVED",
            reason="可执行",
            evidence_json='{"safe": true}',
            created_at=datetime(2026, 8, 29, 8, 16, 0),
            updated_at=datetime(2026, 8, 29, 8, 16, 0),
        )
        audit_review = AuditRecord(
            id=2,
            task_id=2,
            dispatch_id=2,
            result="REVIEW_REQUIRED",
            reason="道路封闭",
            evidence_json='{"secret": "not-a-read-model-field"}',
            created_at=REVIEW_TIME,
            updated_at=REVIEW_TIME,
        )
        running_thread = RuntimeThread(
            id=1,
            thread_id="thread-approved-1",
            task_id="TASK-approved-1",
            status="RUNNING",
            current_checkpoint_id="checkpoint-approved-1",
            state_version=3,
            current_node="routing",
            next_node="audit",
            checkpoint_count=3,
            checkpoint_size_bytes=1024,
            worker_consumer="worker-a",
            resumed_count=0,
            created_at=datetime(2026, 8, 29, 8, 20, 0),
            updated_at=datetime(2026, 8, 29, 8, 20, 0),
        )
        terminal_thread = RuntimeThread(
            id=2,
            thread_id="thread-review-2",
            task_id="TASK-review-2",
            status="TERMINAL",
            current_checkpoint_id="checkpoint-review-2",
            state_version=5,
            current_node="audit",
            next_node=None,
            checkpoint_count=5,
            checkpoint_size_bytes=2048,
            worker_consumer="worker-b",
            resumed_count=1,
            terminal_at=REVIEW_TIME,
            created_at=REVIEW_TIME,
            updated_at=REVIEW_TIME,
        )
        session.add_all(
            [
                order_one,
                order_two,
                order_three,
                anomaly_one,
                anomaly_two,
                task_approved,
                task_review,
                task_latest,
                task_operator,
                task_inactive_dispatcher,
                dispatcher_one,
                dispatcher_two,
                operator,
                inactive_dispatcher,
                dispatch_approved,
                dispatch_review,
                audit_approved,
                audit_review,
                running_thread,
                terminal_thread,
            ]
        )
        session.commit()


def seed_tasks_without_demo_employees(factory) -> None:
    with factory() as session:
        order = Order(
            id=100,
            order_no="LIVE-ORDER-100",
            status="PENDING",
            driver_id=None,
            vehicle_id=None,
            route_id=None,
            origin="北山镇",
            destination="县城分拨中心",
            created_at=datetime(2026, 8, 29, 12, 0, 0),
            updated_at=datetime(2026, 8, 29, 12, 0, 0),
        )
        task = DispatchTask(
            id=100,
            task_id="TASK-unscoped-100",
            order_id=100,
            anomaly_id=None,
            status="APPROVED",
            idempotency_key="unscoped-100",
            assignee_subject_id=None,
            created_at=datetime(2026, 8, 29, 12, 5, 0),
            updated_at=datetime(2026, 8, 29, 12, 5, 0),
        )
        session.add_all([order, task])
        session.commit()


def test_list_team_tasks_returns_only_active_dispatcher_tasks_with_invariant_summaries(
    sqlite_factory,
):
    from app.workspace_reads.models import TeamTaskSummary
    from app.workspace_reads.sqlalchemy_repository import SqlAlchemyWorkspaceReadRepository

    seed_workspace(sqlite_factory)

    page = SqlAlchemyWorkspaceReadRepository(sqlite_factory).list_team_tasks(
        assignee_subject_id=None,
        limit=20,
        before_id=None,
        state=None,
    )

    assert [item.task_id for item in page.items] == [
        "TASK-latest-3",
        "TASK-review-2",
        "TASK-approved-1",
    ]
    assert page.summary == TeamTaskSummary(total=3, ready=2, waiting=1, active=0, ended=0)
    assert [(member.subject_id, member.total) for member in page.members] == [
        ("dispatcher-1", 2),
        ("dispatcher-2", 1),
    ]


def test_list_team_tasks_filters_member_and_state_without_changing_team_summaries(sqlite_factory):
    from app.workspace_reads.models import TeamTaskSummary
    from app.workspace_reads.sqlalchemy_repository import SqlAlchemyWorkspaceReadRepository

    seed_workspace(sqlite_factory)

    page = SqlAlchemyWorkspaceReadRepository(sqlite_factory).list_team_tasks(
        assignee_subject_id="dispatcher-2",
        limit=20,
        before_id=None,
        state="READY",
    )

    assert [item.task_id for item in page.items] == ["TASK-latest-3"]
    assert page.total == 1
    assert page.summary == TeamTaskSummary(total=3, ready=2, waiting=1, active=0, ended=0)
    assert [(member.subject_id, member.total) for member in page.members] == [
        ("dispatcher-1", 2),
        ("dispatcher-2", 1),
    ]


def test_list_team_tasks_rejects_non_dispatcher_member(sqlite_factory):
    from app.workspace_reads.exceptions import TeamMemberNotFound
    from app.workspace_reads.sqlalchemy_repository import SqlAlchemyWorkspaceReadRepository

    seed_workspace(sqlite_factory)

    with pytest.raises(TeamMemberNotFound) as raised:
        SqlAlchemyWorkspaceReadRepository(sqlite_factory).list_team_tasks(
            assignee_subject_id="operator-1",
            limit=20,
            before_id=None,
            state=None,
        )

    assert raised.value.subject_id == "operator-1"


def test_list_team_tasks_uses_stable_cursor_without_repeating_tasks(sqlite_factory):
    from app.workspace_reads.sqlalchemy_repository import SqlAlchemyWorkspaceReadRepository

    seed_workspace(sqlite_factory)
    repository = SqlAlchemyWorkspaceReadRepository(sqlite_factory)

    first = repository.list_team_tasks(
        assignee_subject_id=None,
        limit=1,
        before_id=None,
        state=None,
    )
    second = repository.list_team_tasks(
        assignee_subject_id=None,
        limit=1,
        before_id=int(first.next_cursor),
        state=None,
    )

    assert [item.task_id for item in first.items] == ["TASK-latest-3"]
    assert first.next_cursor == "3"
    assert [item.task_id for item in second.items] == ["TASK-review-2"]
    assert second.next_cursor == "2"
    assert first.items[0].task_id != second.items[0].task_id


def test_list_team_tasks_without_demo_dispatchers_returns_safe_empty_page(sqlite_factory):
    from app.workspace_reads.models import TeamTaskSummary
    from app.workspace_reads.sqlalchemy_repository import SqlAlchemyWorkspaceReadRepository

    seed_tasks_without_demo_employees(sqlite_factory)

    page = SqlAlchemyWorkspaceReadRepository(sqlite_factory).list_team_tasks(
        assignee_subject_id=None,
        limit=20,
        before_id=None,
        state=None,
    )

    assert page.items == ()
    assert page.members == ()
    assert page.summary == TeamTaskSummary(total=0, ready=0, waiting=0, active=0, ended=0)
    assert page.total == 0
    assert page.next_cursor is None


def test_list_reviews_returns_only_review_required_with_safe_joined_fields(sqlite_factory):
    from app.workspace_reads.models import ReviewListItem
    from app.workspace_reads.sqlalchemy_repository import SqlAlchemyWorkspaceReadRepository

    seed_workspace(sqlite_factory)
    repository = SqlAlchemyWorkspaceReadRepository(sqlite_factory)

    page = repository.list_reviews(limit=20, before_id=None)

    assert page.total == 1
    assert page.items == (
        ReviewListItem(
            row_id=2,
            task_id="TASK-review-2",
            order_no="DEMO-ORDER-002",
            risk="HIGH",
            reason="道路封闭",
            vehicle_id="苏G·N2148",
            original_route_id="东河乡道",
            suggested_route_id=None,
            status="REVIEW_REQUIRED",
            created_at=REVIEW_TIME,
            ai_analysis_reason="道路封闭",
            ai_recommended_action="停在安全位置并等待调度配置替代路线。",
            ai_analysis_mode="EIGHT_AGENT_RULE_ASSISTED",
            issue_subtype="CLOSURE",
        ),
    )


def test_list_my_tasks_isolates_owner_and_returns_literal_summary(sqlite_factory):
    from app.workspace_reads.models import MyTaskListItem, MyTaskSummary
    from app.workspace_reads.sqlalchemy_repository import SqlAlchemyWorkspaceReadRepository

    seed_workspace(sqlite_factory)
    repository = SqlAlchemyWorkspaceReadRepository(sqlite_factory)

    page = repository.list_my_tasks(
        subject_id="dispatcher-1",
        limit=20,
        before_id=None,
        state=None,
    )

    assert page.total == 2
    assert page.next_cursor is None
    assert page.provenance == "LIVE"
    assert page.summary == MyTaskSummary(total=2, ready=1, waiting=1, active=0, ended=0)
    assert page.items == (
        MyTaskListItem(
            row_id=2,
            task_id="TASK-review-2",
            order_no="DEMO-ORDER-002",
            risk="HIGH",
            description="道路封闭",
            vehicle_id="苏G·N2148",
            original_route_id="东河乡道",
            suggested_route_id=None,
                status="REVIEW_REQUIRED",
                created_at=REVIEW_TIME,
                updated_at=REVIEW_TIME,
                origin="东河镇",
                destination="县城分拨中心",
                publication_status="PENDING",
            ),
        MyTaskListItem(
            row_id=1,
            task_id="TASK-approved-1",
            order_no="DEMO-ORDER-001",
            risk="LOW",
            description="降雨",
            vehicle_id="苏G·N2147",
            original_route_id="西河乡道",
                suggested_route_id=None,
                status="APPROVED",
                created_at=datetime(2026, 8, 29, 8, 10, 0),
                updated_at=datetime(2026, 8, 29, 8, 10, 0),
                origin="青云镇",
                destination="临港镇",
                publication_status="PENDING",
            ),
    )
    assert all(item.task_id != "TASK-latest-3" for item in page.items)


def test_list_my_tasks_withholds_the_route_until_it_is_published(sqlite_factory):
    from app.workspace_reads.sqlalchemy_repository import SqlAlchemyWorkspaceReadRepository

    seed_workspace(sqlite_factory)

    page = SqlAlchemyWorkspaceReadRepository(sqlite_factory).list_my_tasks(
        subject_id="dispatcher-1",
        limit=20,
        before_id=None,
        state="READY",
    )

    item = page.items[0]
    assert item.task_id == "TASK-approved-1"
    assert item.suggested_route_id is None
    assert item.publication_status == "PENDING"
    assert item.route_instruction is None
    assert (item.origin, item.destination) == ("青云镇", "临港镇")


def test_list_my_tasks_exposes_only_the_published_route_and_instruction(sqlite_factory):
    from app.workspace_reads.sqlalchemy_repository import SqlAlchemyWorkspaceReadRepository

    seed_workspace(sqlite_factory)
    with sqlite_factory() as session:
        session.add(
            DispatchPublication(
                task_id=1,
                dispatch_id=1,
                status="PUBLISHED",
                route_id="西河乡道-绕行",
                route_instruction="从青云镇出发，经西河乡道-绕行前往临港镇。",
                published_by_subject_id="supervisor-1",
                published_by_display_name="调度主管",
                published_at=REVIEW_TIME,
            )
        )
        session.commit()

    page = SqlAlchemyWorkspaceReadRepository(sqlite_factory).list_my_tasks(
        subject_id="dispatcher-1",
        limit=20,
        before_id=None,
        state="READY",
    )

    item = page.items[0]
    assert item.suggested_route_id == "西河乡道-绕行"
    assert item.publication_status == "PUBLISHED"
    assert item.route_instruction == "从青云镇出发，经西河乡道-绕行前往临港镇。"
    assert item.published_at == REVIEW_TIME


def test_list_my_tasks_filters_state_without_changing_owner_summary(sqlite_factory):
    from app.workspace_reads.models import MyTaskSummary
    from app.workspace_reads.sqlalchemy_repository import SqlAlchemyWorkspaceReadRepository

    seed_workspace(sqlite_factory)
    repository = SqlAlchemyWorkspaceReadRepository(sqlite_factory)

    page = repository.list_my_tasks(
        subject_id="dispatcher-1",
        limit=20,
        before_id=None,
        state="READY",
    )

    assert [item.task_id for item in page.items] == ["TASK-approved-1"]
    assert page.total == 1
    assert page.summary == MyTaskSummary(total=2, ready=1, waiting=1, active=0, ended=0)


def test_list_my_tasks_uses_latest_dispatch_and_stable_cursor(sqlite_factory):
    from app.workspace_reads.sqlalchemy_repository import SqlAlchemyWorkspaceReadRepository

    seed_workspace(sqlite_factory)
    with sqlite_factory() as session:
        session.add(
            Dispatch(
                id=4,
                dispatch_no="DISPATCH-004",
                order_id=2,
                task_id=2,
                original_route_id="东河乡道-新",
                target_route_id="国道-最新方案",
                decision_reason="最新方案",
                status="PENDING_REVIEW",
                created_at=REVIEW_TIME,
                updated_at=REVIEW_TIME,
            )
        )
        session.commit()
    repository = SqlAlchemyWorkspaceReadRepository(sqlite_factory)

    first = repository.list_my_tasks(subject_id="dispatcher-1", limit=1, before_id=None, state=None)
    second = repository.list_my_tasks(
        subject_id="dispatcher-1",
        limit=1,
        before_id=int(first.next_cursor),
        state=None,
    )

    assert first.total == 2
    assert first.next_cursor == "2"
    assert first.items[0].original_route_id == "东河乡道-新"
    assert first.items[0].suggested_route_id is None
    assert first.items[0].publication_status == "PENDING"
    assert [item.row_id for item in second.items] == [1]
    assert second.next_cursor is None


def test_list_reviews_uses_one_deterministic_latest_dispatch_and_audit_per_task(sqlite_factory):
    from app.workspace_reads.models import ReviewListItem
    from app.workspace_reads.sqlalchemy_repository import SqlAlchemyWorkspaceReadRepository

    seed_workspace(sqlite_factory)
    with sqlite_factory() as session:
        session.add(
            Dispatch(
                id=3,
                dispatch_no="DISPATCH-003",
                order_id=2,
                task_id=2,
                original_route_id="东河乡道-旧",
                target_route_id="国道-102",
                decision_reason="最新绕行方案",
                recommended_action="按核验路线安全绕行。",
                analysis_mode="EIGHT_AGENT_RULE_ASSISTED",
                issue_subtype="CLOSURE",
                status="PENDING_REVIEW",
                created_at=REVIEW_TIME,
                updated_at=REVIEW_TIME,
            )
        )
        session.flush()
        session.add_all(
            [
                AuditRecord(
                    id=3,
                    task_id=2,
                    dispatch_id=3,
                    result="REVIEW_REQUIRED",
                    reason="旧复核原因",
                    evidence_json="{}",
                    created_at=REVIEW_TIME,
                    updated_at=REVIEW_TIME,
                ),
                AuditRecord(
                    id=4,
                    task_id=2,
                    dispatch_id=3,
                    result="REVIEW_REQUIRED",
                    reason="最新复核原因",
                    evidence_json="{}",
                    created_at=REVIEW_TIME,
                    updated_at=REVIEW_TIME,
                ),
            ]
        )
        session.commit()

    page = SqlAlchemyWorkspaceReadRepository(sqlite_factory).list_reviews(limit=1, before_id=None)

    assert page.total == 1
    assert page.next_cursor is None
    assert page.items == (
        ReviewListItem(
            row_id=2,
            task_id="TASK-review-2",
            order_no="DEMO-ORDER-002",
            risk="HIGH",
            reason="最新绕行方案",
            vehicle_id="苏G·N2148",
            original_route_id="东河乡道-旧",
            suggested_route_id="国道-102",
            status="REVIEW_REQUIRED",
            created_at=REVIEW_TIME,
            ai_analysis_reason="最新绕行方案",
            ai_recommended_action="按核验路线安全绕行。",
            ai_analysis_mode="EIGHT_AGENT_RULE_ASSISTED",
            issue_subtype="CLOSURE",
        ),
    )


def test_order_and_anomaly_filters_return_literal_matching_projections(sqlite_factory):
    from app.workspace_reads.models import AnomalyListItem, OrderListItem
    from app.workspace_reads.sqlalchemy_repository import SqlAlchemyWorkspaceReadRepository

    seed_workspace(sqlite_factory)
    repository = SqlAlchemyWorkspaceReadRepository(sqlite_factory)

    orders = repository.list_orders(limit=20, before_id=None, query="东河", status="DELAYED")
    anomalies = repository.list_anomalies(limit=20, before_id=None, query="DEMO-ORDER-002", risk="HIGH", status="OPEN")

    assert orders.total == 1
    assert orders.items == (
        OrderListItem(
            row_id=2,
            order_no="DEMO-ORDER-002",
            status="DELAYED",
            driver_id="driver-2",
            vehicle_id="苏G·N2148",
            route_id="东河乡道",
            origin="东河镇",
            destination="县城分拨中心",
            created_at=REVIEW_TIME,
            updated_at=REVIEW_TIME,
            anomaly_count=1,
            latest_task_id="TASK-latest-3",
        ),
    )
    assert anomalies.total == 1
    assert anomalies.items == (
        AnomalyListItem(
            row_id=2,
            anomaly_no="DEMO-ANOM-002",
            order_no="DEMO-ORDER-002",
            driver_id="driver-2",
            vehicle_id="苏G·N2148",
            route_id="东河乡道",
            latest_task_id="TASK-latest-3",
            anomaly_type="ROAD",
            risk="HIGH",
            description="道路封闭",
            status="OPEN",
            reported_at=REVIEW_TIME,
        ),
    )
    assert orders.provenance == "DEMO"
    assert anomalies.provenance == "DEMO"


def test_order_and_anomaly_provenance_uses_the_full_filtered_collection(sqlite_factory):
    from app.workspace_reads.sqlalchemy_repository import SqlAlchemyWorkspaceReadRepository

    seed_workspace(sqlite_factory)
    repository = SqlAlchemyWorkspaceReadRepository(sqlite_factory)

    demo_orders = repository.list_orders(limit=1, before_id=None, query="DEMO-ORDER", status=None)
    live_orders = repository.list_orders(limit=1, before_id=None, query="LIVE-ORDER", status=None)
    mixed_orders = repository.list_orders(limit=1, before_id=None, query=None, status=None)
    demo_anomalies = repository.list_anomalies(limit=1, before_id=None, query="DEMO-ANOM", risk=None, status=None)
    live_anomalies = repository.list_anomalies(limit=1, before_id=None, query="LIVE-ANOM", risk=None, status=None)
    mixed_anomalies = repository.list_anomalies(limit=1, before_id=None, query=None, risk=None, status=None)

    assert (demo_orders.total, demo_orders.provenance) == (2, "DEMO")
    assert (live_orders.total, live_orders.provenance) == (1, "LIVE")
    assert (mixed_orders.total, mixed_orders.provenance) == (3, "MIXED")
    assert (demo_anomalies.total, demo_anomalies.provenance) == (1, "DEMO")
    assert (live_anomalies.total, live_anomalies.provenance) == (1, "LIVE")
    assert (mixed_anomalies.total, mixed_anomalies.provenance) == (2, "MIXED")


def test_before_id_uses_stable_descending_cursor_and_exact_filtered_total(sqlite_factory):
    from app.workspace_reads.sqlalchemy_repository import SqlAlchemyWorkspaceReadRepository

    seed_workspace(sqlite_factory)
    repository = SqlAlchemyWorkspaceReadRepository(sqlite_factory)

    first_page = repository.list_orders(limit=2, before_id=None, query=None, status=None)
    second_page = repository.list_orders(limit=2, before_id=int(first_page.next_cursor), query=None, status=None)

    assert first_page.total == 3
    assert [item.row_id for item in first_page.items] == [3, 2]
    assert first_page.next_cursor == "2"
    assert second_page.total == 3
    assert [item.row_id for item in second_page.items] == [1]
    assert second_page.next_cursor is None


def test_list_orders_defaults_to_twenty_and_rejects_out_of_range_limits(sqlite_factory):
    from app.workspace_reads.sqlalchemy_repository import SqlAlchemyWorkspaceReadRepository

    seed_workspace(sqlite_factory)
    repository = SqlAlchemyWorkspaceReadRepository(sqlite_factory)

    default_page = repository.list_orders(before_id=None, query=None, status=None)

    assert [item.row_id for item in default_page.items] == [3, 2, 1]
    with pytest.raises(ValueError, match="limit must be between 1 and 100"):
        repository.list_orders(limit=0, before_id=None, query=None, status=None)
    with pytest.raises(ValueError, match="limit must be between 1 and 100"):
        repository.list_orders(limit=101, before_id=None, query=None, status=None)


def test_runtime_threads_expose_safe_fields_only_and_count_domains_exactly(sqlite_factory):
    from app.workspace_reads.models import DomainCounts, RuntimeThreadListItem
    from app.workspace_reads.sqlalchemy_repository import SqlAlchemyWorkspaceReadRepository

    seed_workspace(sqlite_factory)
    repository = SqlAlchemyWorkspaceReadRepository(sqlite_factory)

    page = repository.list_runtime_threads(limit=20, before_id=None, status="TERMINAL")

    assert page.total == 1
    assert page.items == (
        RuntimeThreadListItem(
            row_id=2,
            thread_id="thread-review-2",
            task_id="TASK-review-2",
            status="TERMINAL",
            current_node="audit",
            next_node=None,
            state_version=5,
            checkpoint_count=5,
            worker_consumer="worker-b",
            terminal_at=REVIEW_TIME,
            updated_at=REVIEW_TIME,
        ),
    )
    assert not hasattr(page.items[0], "checkpoint_payload")
    assert not hasattr(page.items[0], "checkpoint_body")
    assert repository.count_domains() == DomainCounts(
        orders=3,
        anomalies=2,
        reviews=1,
        runtime_threads=2,
        provenance="MIXED",
    )
