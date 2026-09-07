import importlib.util
import os
from pathlib import Path
from types import ModuleType
from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine, inspect
from sqlalchemy.engine import URL
from sqlalchemy.exc import IntegrityError

from app.models.dispatch import Dispatch

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "alembic"
    / "versions"
    / "20260907_14_dispatch_task_uniqueness.py"
)


def _load_migration() -> ModuleType:
    spec = importlib.util.spec_from_file_location("dispatch_task_uniqueness", MIGRATION_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _dispatches(metadata: MetaData) -> Table:
    return Table(
        "dispatches",
        metadata,
        Column("id", Integer, primary_key=True),
        Column("dispatch_no", String(64), nullable=False),
        Column("task_id", Integer, nullable=True),
    )


def test_dispatch_orm_declares_one_dispatch_per_task() -> None:
    names = {
        constraint.name
        for constraint in Dispatch.__table__.constraints
        if isinstance(constraint, sa.UniqueConstraint)
    }
    assert "uq_dispatches_task_id" in names


def test_dispatch_task_uniqueness_migration_upgrades_and_downgrades_sqlite() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    metadata = MetaData()
    dispatches = _dispatches(metadata)
    metadata.create_all(engine)
    module = _load_migration()

    with engine.begin() as connection:
        connection.execute(
            dispatches.insert(),
            [
                {"id": 1, "dispatch_no": "DSP-1", "task_id": 1},
                {"id": 2, "dispatch_no": "DSP-2", "task_id": 2},
            ],
        )
        original_op = module.op
        module.op = Operations(MigrationContext.configure(connection))
        try:
            module.upgrade()
            assert "uq_dispatches_task_id" in {
                item["name"]
                for item in inspect(connection).get_unique_constraints("dispatches")
            }
            with pytest.raises(IntegrityError):
                connection.execute(
                    dispatches.insert().values(
                        id=3,
                        dispatch_no="DSP-DUPLICATE-BLOCKED",
                        task_id=1,
                    )
                )

            module.downgrade()
            assert "uq_dispatches_task_id" not in {
                item["name"]
                for item in inspect(connection).get_unique_constraints("dispatches")
            }
            connection.execute(
                dispatches.insert().values(
                    id=3,
                    dispatch_no="DSP-DUPLICATE-ALLOWED",
                    task_id=1,
                )
            )
        finally:
            module.op = original_op
    engine.dispose()


def _mysql_urls() -> tuple[URL, URL, str]:
    env_path = os.getenv("COUNTYFLOW_MYSQL_INTEGRATION_DOCKER_ENV")
    if not env_path or not Path(env_path).is_file():
        pytest.skip("未设置可用的 opt-in MySQL 环境文件")
    values: dict[str, str] = {}
    for line in Path(env_path).read_text(encoding="utf-8").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
    if not values.get("MYSQL_ROOT_PASSWORD"):
        pytest.skip("opt-in MySQL 环境文件缺少所需配置")
    database = f"countyflow_task6_unique_{uuid4().hex}"
    host = os.getenv("COUNTYFLOW_MYSQL_INTEGRATION_HOST", "127.0.0.1")
    port = int(os.getenv("COUNTYFLOW_MYSQL_INTEGRATION_PORT", "3306"))
    admin = URL.create(
        "mysql+pymysql",
        username="root",
        password=values["MYSQL_ROOT_PASSWORD"],
        host=host,
        port=port,
    )
    target = URL.create(
        "mysql+pymysql",
        username="root",
        password=values["MYSQL_ROOT_PASSWORD"],
        host=host,
        port=port,
        database=database,
    )
    return admin, target, database


def test_dispatch_task_uniqueness_migration_mysql_round_trip() -> None:
    admin_url, database_url, database = _mysql_urls()
    assert "***" in str(admin_url) and "***" in str(database_url)
    admin = create_engine(admin_url, future=True)
    engine = None
    module = _load_migration()
    try:
        with admin.begin() as connection:
            connection.execute(
                sa.text(f"CREATE DATABASE `{database}` CHARACTER SET utf8mb4")
            )
        engine = create_engine(database_url, future=True)
        metadata = MetaData()
        _dispatches(metadata)
        metadata.create_all(engine)
        with engine.begin() as connection:
            original_op = module.op
            module.op = Operations(MigrationContext.configure(connection))
            try:
                module.upgrade()
                assert "uq_dispatches_task_id" in {
                    item["name"]
                    for item in inspect(connection).get_unique_constraints("dispatches")
                }
                module.downgrade()
                assert "uq_dispatches_task_id" not in {
                    item["name"]
                    for item in inspect(connection).get_unique_constraints("dispatches")
                }
            finally:
                module.op = original_op
    finally:
        if engine is not None:
            engine.dispose()
        with admin.begin() as connection:
            connection.execute(sa.text(f"DROP DATABASE IF EXISTS `{database}`"))
        admin.dispose()

def test_dispatch_task_uniqueness_migration_continues_from_current_head() -> None:
    module = _load_migration()
    assert module.revision == "20260907_14"
    assert module.down_revision == "20260902_13"