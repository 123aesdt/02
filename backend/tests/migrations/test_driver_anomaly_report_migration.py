from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from sqlalchemy import UniqueConstraint

from app.models.anomaly import Anomaly


def test_anomaly_model_exposes_driver_report_provenance() -> None:
    table = Anomaly.__table__

    assert {
        "reported_by_subject_id",
        "source_task_id",
        "location_text",
        "reported_vehicle_status",
        "report_idempotency_key",
    } <= set(table.columns.keys())
    assert any(
        isinstance(constraint, UniqueConstraint)
        and constraint.name == "uq_anomalies_report_idempotency_key"
        for constraint in table.constraints
    )


def test_driver_report_migration_continues_from_current_head() -> None:
    migration_path = (
        Path(__file__).parents[2]
        / "alembic"
        / "versions"
        / "20260901_11_driver_anomaly_reports.py"
    )
    assert migration_path.exists()

    spec = spec_from_file_location("driver_anomaly_reports_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.revision == "20260901_11"
    assert migration.down_revision == "20260830_10"
