import os
import uuid

import pytest
from devices import DEVICE, MANUAL
from falkordb import FalkorDB
from redis.exceptions import RedisError

from lighthouse import ensure_schema


def connect() -> FalkorDB:
    return FalkorDB(
        host=os.environ.get("FALKORDB_HOST", "127.0.0.1"),
        port=int(os.environ.get("FALKORDB_PORT", "26379")),
    )


@pytest.fixture(scope="session")
def db():
    db = connect()
    try:
        db.list_graphs()
    except RedisError as exc:
        pytest.fail(f"FalkorDB is not reachable ({exc}). Start it with `docker compose up -d`.")
    return db


@pytest.fixture
def graph(db):
    """A throwaway graph with the schema of the test domain. Tests never touch a real graph."""
    graph = db.select_graph(f"test_{uuid.uuid4().hex}")
    ensure_schema(graph, [DEVICE, MANUAL])
    yield graph
    graph.delete()
