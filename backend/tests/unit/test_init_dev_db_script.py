from pathlib import Path


def test_init_dev_db_script_uses_alembic_without_destructive_database_commands():
    script = Path(__file__).parents[3] / "scripts" / "init-dev-db.ps1"

    contents = script.read_text(encoding="utf-8")

    assert "alembic" in contents.lower()
    assert "upgrade head" in contents.lower()
    assert "create_all" not in contents.lower()
    assert "remove-item" not in contents.lower()
