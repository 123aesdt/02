from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

PROJECT_ROOT = Path(__file__).resolve().parents[3]


def test_repository_recognizes_persisted_dispatch_uniqueness_revision() -> None:
    config = Config(str(PROJECT_ROOT / "backend" / "alembic.ini"))
    config.set_main_option(
        "script_location",
        str(PROJECT_ROOT / "backend" / "alembic"),
    )
    migrations = ScriptDirectory.from_config(config)

    revision = migrations.get_revision("20260907_14")

    assert revision is not None
    assert revision.down_revision == "20260902_13"
    assert migrations.get_current_head() == "20260907_14"
