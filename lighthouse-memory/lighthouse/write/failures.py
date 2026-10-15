"""Failures: a write that did not happen is stored as a WriteFailure node, so that it is never
lost silently. The same refusal again, such as a bad record that a feed sends on every
read, is counted on the node it made the first time: `times` and `last_at` grow, and the
graph does not."""

import hashlib
import json

from falkordb import Graph

from lighthouse.clock import now
from lighthouse.values import MAX_DETAIL, is_key, is_name, named


def record_failure(
    graph: Graph, reason: str, kind: str | None = None, key=None, detail=None, owner=None
):
    """Store a write that did not happen, so it is never lost silently.

    What is stored is bounded and safe, whatever the refused write held: `detail` is cut to
    2,000 characters, and a kind or key that is not a valid one is left out. `owner` names
    the user whose content the refused write held, so that it can be erased with the rest."""
    named(reason=reason)
    if detail is not None:
        # The detail may quote hostile input. Keep it short, and keep it text FalkorDB takes.
        detail = str(detail)[:MAX_DETAIL].replace("\x00", "\\x00")
        detail = detail.encode("utf-8", "backslashreplace").decode("utf-8")
    params = {
        "now": now(),
        "reason": reason,
        "kind": kind if is_name(kind) else None,
        "key": key if is_key(key) else None,
        "detail": detail,
        "owner": owner if is_name(owner) else None,
    }
    fields = [params[name] for name in ("reason", "kind", "key", "detail", "owner")]
    params["same"] = hashlib.sha256(json.dumps(fields, default=str).encode()).hexdigest()
    graph.query(
        "MERGE (f:WriteFailure {same: $same}) "
        "ON CREATE SET f.at = localdatetime($now), f.reason = $reason, f.kind = $kind, "
        "f.key = $key, f.detail = $detail, f.owner = $owner, f.times = 1 "
        "ON MATCH SET f.times = f.times + 1 "
        "SET f.last_at = localdatetime($now)",
        params,
    )
