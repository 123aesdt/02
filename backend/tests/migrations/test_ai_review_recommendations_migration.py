from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

from app.models.dispatch import Dispatch
from app.models.dispatch_publication import DispatchPublication


def test_models_expose_ai_review_and_action_publication_fields() -> None:
    dispatch_columns = Dispatch.__table__.columns
    publication_columns = DispatchPublication.__table__.columns

    assert {"recommended_action", "analysis_mode", "issue_subtype"} <= set(dispatch_columns.keys())
    assert "action_instruction" in publication_columns
    assert publication_columns["route_id"].nullable is True
    assert publication_columns["route_instruction"].nullable is True


def test_ai_review_migration_continues_from_current_head() -> None:
    migration_path = (
        Path(__file__).parents[2]
        / "alembic"
        / "versions"
        / "20260901_12_ai_review_recommendations.py"
    )
    assert migration_path.exists()

    spec = spec_from_file_location("ai_review_recommendations_migration", migration_path)
    assert spec is not None and spec.loader is not None
    migration = module_from_spec(spec)
    spec.loader.exec_module(migration)

    assert migration.revision == "20260901_12"
    assert migration.down_revision == "20260901_11"
