import uuid

import pytest
from lighthouse import ensure_schema
from redis.exceptions import RedisError

from app.db import get_db
from app.portcalls import KINDS


@pytest.fixture(scope="session")
def db():
    db = get_db()
    try:
        db.list_graphs()
    except RedisError as exc:
        pytest.fail(f"FalkorDB is not reachable ({exc}). Start it with `docker compose up -d`.")
    return db


@pytest.fixture
def graph(db):
    """A throwaway graph with the port desk schema. Tests never touch the `world` graph."""
    graph = db.select_graph(f"test_{uuid.uuid4().hex}")
    ensure_schema(graph, KINDS)
    yield graph
    graph.delete()
