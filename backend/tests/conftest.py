from collections.abc import Iterator
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.models.base import Base


@pytest.fixture
def sqlite_factory() -> Iterator[sessionmaker[Session]]:
    import app.models.runtime_override  # noqa: F401
    import app.models.runtime_thread  # noqa: F401
    import app.models.security_audit  # noqa: F401
    import app.models.shared_memory  # noqa: F401

    with TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
        engine = create_engine(f"sqlite+pysqlite:///{Path(temp_dir) / 'shared-memory.db'}")
        Base.metadata.create_all(engine)
        factory = sessionmaker(bind=engine, expire_on_commit=False)
        yield factory
        engine.dispose()
