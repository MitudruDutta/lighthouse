"""Promotion: what repeats in episodes that ended becomes a lesson or a playbook.

The library does not know what a repeat is. The application passes a rule: a function that
reads one episode that ended and says what it shows, as claims:

  {"lesson": id, "statement": text, "about": [(Kind, key)], "agrees": True or False}
      the episode is evidence for the lesson, or against it
  {"playbook": name, "trigger": {...}, "steps": [{...}]}
      the episode shows these steps working in this situation
  {"ran": name, "succeeded": True or False}
      a playbook ran in the episode, and this is how it went

promote() reads every episode that ended, gathers the claims, and writes what they add up
to. A lesson is learned when enough episodes agree with it; after that, each new episode
weighs it. A playbook is written when enough episodes show the same steps, and a new version
when they show other steps. A run is judged once. Each of these counts an episode once, so
promote() can run as often as the application likes and writes nothing twice.
"""

import json

from falkordb import Graph

from lighthouse.episodes import ended, episode
from lighthouse.lessons import learn, lesson, weigh
from lighthouse.playbooks import NEEDS, playbook, ran, write_playbook
from lighthouse.values import MAX_REFERENCES, describe, named, properties, whole_number

# What each kind of claim must have, and may have besides.
NEEDED = {"lesson": {"statement", "agrees"}, "playbook": {"trigger", "steps"}, "ran": {"succeeded"}}
OPTIONAL = {"lesson": {"about"}, "playbook": set(), "ran": set()}


def _claims(found: dict, rule) -> list[dict]:
    """What the rule says about one episode, checked. A rule that says something else is a
    mistake of the application, and it stops the promotion before it writes."""
    claims = rule(found)
    if not isinstance(claims, list):
        raise TypeError(f"the rule must give a list of claims, not {type(claims).__name__}")
    for claim in claims:
        kinds = [kind for kind in NEEDED if isinstance(claim, dict) and kind in claim]
        if not kinds:
            raise ValueError(f"not a claim: {describe(claim)}")
        given = set(claim) - {kinds[0]}
        if not NEEDED[kinds[0]] <= given <= NEEDED[kinds[0]] | OPTIONAL[kinds[0]]:
            raise ValueError(
                f"a {kinds[0]} claim has {sorted(NEEDED[kinds[0]])}: {describe(claim)}"
            )
        if type(claim.get("agrees", claim.get("succeeded", True))) is not bool:
            raise ValueError(
                f"in a claim, agrees and succeeded are True or False: {describe(claim)}"
            )
    return claims


def _shape(trigger, steps) -> str:
    """A playbook's trigger and steps as one text, to tell two versions apart. A null value
    is absent, as it is when stored."""
    trigger = properties(trigger, set(), "trigger")
    steps = [properties(step, set(), "step") for step in steps]
    return json.dumps([trigger, steps], sort_keys=True)


def _lesson(graph: Graph, by: str, lesson_id: str, said: list, at_least: int) -> dict:
    agree = [episode_id for episode_id, claim in said if claim["agrees"]]
    disagree = [episode_id for episode_id, claim in said if not claim["agrees"]]
    weighed = agree + disagree
    if lesson(graph, lesson_id) is None:
        if len(agree) < at_least:
            return {"id": lesson_id, "status": "waiting", "for": len(agree)}
        first = next(claim for _, claim in said if claim["agrees"])
        # A lesson is learned from at most so many episodes. The rest weigh it after.
        rests_on, weighed = agree[:MAX_REFERENCES], agree[MAX_REFERENCES:] + disagree
        receipt = learn(graph, lesson_id, by, first["statement"], rests_on, first.get("about", ()))
        if receipt["status"] != "learned":
            return receipt | {"id": lesson_id}  # a refusal names no id: say which it was
    receipts = [weigh(graph, lesson_id, by, item, item in agree) for item in weighed]
    refused = [receipt for receipt in receipts if receipt["status"] not in ("weighed", "exists")]
    if refused:
        return refused[0] | {"id": lesson_id}
    new = sum(receipt["status"] == "weighed" for receipt in receipts)
    status = "learned" if len(weighed) < len(said) else "weighed" if new else "unchanged"
    return {"id": lesson_id, "status": status, "new": new}


def _playbook(graph: Graph, by: str, name: str, said: list, at_least: int) -> dict:
    # The steps that the most episodes show; on a tie, the first in the order of their text.
    shapes: dict[str, list] = {}
    for episode_id, claim in said:
        shapes.setdefault(_shape(claim["trigger"], claim["steps"]), []).append((episode_id, claim))
    shape, shown = min(shapes.items(), key=lambda item: (-len(item[1]), item[0]))
    newest = playbook(graph, name)
    if newest is not None and _shape(newest["trigger"], newest["steps"]) == shape:
        return {"id": newest["id"], "status": "unchanged"}
    if len(shown) < at_least:
        return {"id": name, "status": "waiting", "for": len(shown)}
    claim = shown[0][1]
    episodes = [episode_id for episode_id, _ in shown][:MAX_REFERENCES]
    receipt = write_playbook(graph, name, by, claim["trigger"], claim["steps"], episodes, at_least)
    return receipt if receipt["id"] else receipt | {"id": name}


def promote(graph: Graph, by: str, rule, at_least: int = NEEDS) -> dict:
    """Read every episode that ended, ask `rule` what each one shows, and write what that
    adds up to. `at_least` is how many episodes must agree before a lesson is learned or a
    playbook is written (default 3).

    Returns {"episodes", "lessons", "playbooks", "runs"}: how many episodes were read, and
    a receipt for each lesson, playbook, and run that a claim named. Besides the statuses
    of the library, a receipt can say
      waiting    fewer episodes agree than `at_least`; "for" says how many do
      unchanged  nothing new: every episode is counted, or the playbook has these steps
    A lesson that is learned or weighed says how many episodes were "new" to it.
    """
    named(by=by)
    if not callable(rule):
        raise TypeError("rule must be a function of one episode")
    at_least = whole_number(at_least, "at_least", MAX_REFERENCES)
    # Limit: every ended episode is read, one query each, on every run. Fine for thousands
    # of episodes; beyond that, keep what was read and read only what ended since.
    ids = ended(graph)
    claims = [
        (episode_id, claim)
        for episode_id in ids
        for claim in _claims(episode(graph, episode_id), rule)
    ]
    lessons: dict[str, list] = {}
    playbooks: dict[str, list] = {}
    for episode_id, claim in claims:
        if "lesson" in claim:
            lessons.setdefault(claim["lesson"], []).append((episode_id, claim))
        elif "playbook" in claim:
            playbooks.setdefault(claim["playbook"], []).append((episode_id, claim))
    return {
        "episodes": len(ids),
        "lessons": [_lesson(graph, by, key, said, at_least) for key, said in lessons.items()],
        "playbooks": [_playbook(graph, by, key, said, at_least) for key, said in playbooks.items()],
        "runs": [
            ran(graph, claim["ran"], by, episode_id, claim["succeeded"])
            for episode_id, claim in claims
            if "ran" in claim
        ],
    }
