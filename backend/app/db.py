import os
from functools import cache

from falkordb import FalkorDB


@cache
def get_db() -> FalkorDB:
    """One client for the process. FALKORDB_USERNAME and FALKORDB_PASSWORD are optional:
    set them for any database that is not on this machine."""
    return FalkorDB(
        host=os.environ.get("FALKORDB_HOST", "127.0.0.1"),
        port=int(os.environ.get("FALKORDB_PORT", "26379")),
        username=os.environ.get("FALKORDB_USERNAME") or None,
        password=os.environ.get("FALKORDB_PASSWORD") or None,
    )
