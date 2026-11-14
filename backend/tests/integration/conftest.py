import os
from pathlib import Path
from uuid import uuid4

import pytest
from alembic.config import Config
from sqlalchemy import create_engine, text


@pytest.fixture
def database(monkeypatch):
    """Use an isolated schema, never downgrade an operator's existing schema."""
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.fail("Set TEST_DATABASE_URL to the Compose PostgreSQL URL")
    schema = "test_" + uuid4().hex
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{schema}"'))
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.setenv("PGOPTIONS", f"-csearch_path={schema}")
    isolated = create_engine(url)
    config = Config(str(Path(__file__).parents[2] / "alembic.ini"))
    try:
        yield isolated, config
    finally:
        isolated.dispose()
        with engine.begin() as connection:
            connection.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
        engine.dispose()
