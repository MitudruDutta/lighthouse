"""The Reviewer: turns berth overloads that ended into lessons and playbooks.

Its rule reads one overload episode that ended and says what it shows:

  the berth took them all, or it did not    a lesson about the berth, for or against
  a port call was moved to another berth    a playbook: at the next overload of this berth,
                                            propose the other one
  a playbook ran in the episode             whether a port call went where it proposed

The library's promote() counts these and writes a lesson or a playbook once enough episodes
agree. The Watcher recalls the lesson and follows the playbook at the next overload, and
the next review says whether the playbook was right.
"""

import hashlib
import json

from falkordb import Graph
from lighthouse import promote

from app.portcalls import BERTH
from app.watcher import SITUATION

TAKES = "takes-them"
TURNS = "turns-them-away"


def _name(*parts: str) -> str:
    """An id for a lesson or a playbook, from its parts. An id has at most 200 characters."""
    name = ":".join(parts)
    return (
        name if len(name) <= 200 else f"{parts[0]}:{hashlib.sha256(name.encode()).hexdigest()[:16]}"
    )


def rule(found: dict) -> list[dict]:
    """What one episode that ended shows, as claims for promote()."""
    if not found["id"].startswith(f"{SITUATION}:") or not found["entries"]:
        return []
    seen = next((entry for entry in found["entries"] if entry["type"] == "observation"), None)
    end = found["entries"][-1]
    if seen is None or end["type"] != "outcome" or type(end.get("held")) is not bool:
        return []
    berth, held, moved = seen["berth"], end["held"], end.get("moved_to", [])
    about = [(BERTH, berth)]
    said = f"When more ships are expected at {berth} than were seen there together,"
    claims = [
        {
            "lesson": _name(SITUATION, berth, TAKES),
            "statement": f"{said} the berth takes them all.",
            "about": about,
            "agrees": held,
        },
        {
            "lesson": _name(SITUATION, berth, TURNS),
            "statement": f"{said} not all of them come: port calls are moved or retimed.",
            "about": about,
            "agrees": not held,
        },
    ]
    for other in moved:
        claims.append(
            {
                "playbook": _name(SITUATION, berth, "move-to", other),
                "trigger": {"situation": SITUATION, "berth": berth},
                "steps": [{"do": "propose another berth", "berth": other}],
            }
        )
    # A playbook that ran was right if a port call went to the berth that it proposed.
    proposed: dict[str, set] = {}
    for entry in found["entries"]:
        if entry["type"] == "action" and "playbook" in entry:
            step = json.loads(entry["does"])
            proposed.setdefault(entry["playbook"].rsplit("#", 1)[0], set()).add(step.get("berth"))
    for name, berths in proposed.items():
        claims.append({"ran": name, "succeeded": bool(berths & set(moved))})
    return claims


def review(graph: Graph, by: str = "reviewer") -> dict:
    """Read every episode that ended and write what the overloads add up to. Returns the
    receipts of promote()."""
    return promote(graph, by, rule)
