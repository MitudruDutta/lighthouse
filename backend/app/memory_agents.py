"""Agent coordination over the Memory API: episodes, tasks, and handoffs in a project's graph.

A project key acts as one agent, named by the key: name a key after the agent that uses it.
Who wrote an entry, who claims a task, and who gives or accepts a handoff come from the key,
never from the request. Reads need memory:read; everything that writes needs memory:write.
"""

from typing import Annotated

import lighthouse as memory
from fastapi import APIRouter, Path, Query
from lighthouse.values import is_name
from pydantic import BaseModel, Field

from app.memory_api import FACT, NAME, ReadKey, WriteKey, graph_for, reject, usage_event

router = APIRouter(prefix="/v1")
# Episode and task ids name a path segment of their own, and an entry id is
# "<episode id>/<seq>", so neither may hold a slash.
ID = r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,99}$"
EpisodeId = Annotated[str, Path(pattern=ID)]
TaskId = Annotated[str, Path(pattern=ID)]
HandoffId = Annotated[str, Path(pattern=ID)]
MemoryKey = Annotated[str, Path(pattern=NAME)]
REFUSED = {
    "missing": (422, "Something it refers to does not exist in this project."),
    "invalid": (422, "Check the values and references, then try again."),
    "unknown": (404, "Episode not found."),
    "closed": (409, "This episode is closed."),
    "full": (409, "This episode has reached its entry limit."),
    "failed": (503, "Memory could not be saved. Please try again shortly."),
}


def agent(key: dict) -> str:
    if not is_name(key["name"]):
        reject(403, "Rename this API key to use it as an agent: one line of visible text.")
    return key["name"]


class References(BaseModel):
    """What something rests on or points at, all in this project."""

    entries: list[str] = Field(default_factory=list, max_length=200)
    episodes: list[Annotated[str, Field(pattern=ID)]] = Field(default_factory=list, max_length=200)
    memories: list[Annotated[str, Field(pattern=NAME)]] = Field(
        default_factory=list, max_length=200
    )

    def items(self) -> list:
        return [
            *self.entries,
            *(("Episode", item) for item in self.episodes),
            *((FACT, item) for item in self.memories),
        ]


def receipt(result: dict) -> dict:
    """The receipt of a write, or the refusal it stands for as an HTTP error."""
    if result["status"] in REFUSED:
        reject(*REFUSED[result["status"]])
    return {key: result[key] for key in ("id", "seq", "status") if key in result}


class EpisodeStart(BaseModel):
    id: str = Field(pattern=ID)
    about: list[Annotated[str, Field(pattern=NAME)]] = Field(default_factory=list, max_length=200)


class EntryForm(BaseModel):
    type: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,49}$")
    values: dict = Field(default_factory=dict)
    cites: References = Field(default_factory=References)


class Outcome(BaseModel):
    outcome: dict = Field(default_factory=dict)
    cites: References = Field(default_factory=References)


@router.post("/episodes")
def open_episode(form: EpisodeStart, key: WriteKey):
    graph = graph_for(key["project_id"])
    about = [(FACT, item) for item in form.about]
    result = memory.open_episode(graph, form.id, agent(key), about=about)
    usage_event(key["project_id"], "api.episode", key["id"])
    return receipt(result)


@router.get("/episodes/{episode_id}")
def read_episode(episode_id: EpisodeId, key: ReadKey):
    found = memory.episode(graph_for(key["project_id"]), episode_id)
    usage_event(key["project_id"], "api.episode.read", key["id"])
    if found is None:
        reject(404, "Episode not found.")
    return {"data": found}


@router.post("/episodes/{episode_id}/entries")
def record(episode_id: EpisodeId, form: EntryForm, key: WriteKey):
    if form.type == "outcome":
        reject(422, "Close the episode to record its outcome.")
    graph = graph_for(key["project_id"])
    result = memory.record(
        graph, episode_id, form.type, agent(key), values=form.values, cites=form.cites.items()
    )
    usage_event(key["project_id"], "api.entry", key["id"])
    return receipt(result)


@router.post("/episodes/{episode_id}/close")
def close(episode_id: EpisodeId, form: Outcome, key: WriteKey):
    graph = graph_for(key["project_id"])
    result = memory.close_episode(
        graph, episode_id, agent(key), outcome=form.outcome, cites=form.cites.items()
    )
    usage_event(key["project_id"], "api.entry", key["id"])
    return receipt(result)


@router.get("/memories/{memory_key:path}/episodes")
def episodes_about(memory_key: MemoryKey, key: ReadKey):
    found = memory.episodes_about(graph_for(key["project_id"]), FACT, memory_key)
    usage_event(key["project_id"], "api.episode.read", key["id"])
    return {"data": found}


class TaskForm(BaseModel):
    id: str = Field(pattern=ID)
    kind: str = Field(pattern=r"^[a-z][a-z0-9_.:-]{0,49}$")
    about: str | None = Field(default=None, pattern=NAME)
    after: list[Annotated[str, Field(pattern=ID)]] = Field(default_factory=list, max_length=200)


class ClaimForm(BaseModel):
    kind: str = Field(pattern=r"^[a-z][a-z0-9_.:-]{0,49}$")
    # Seconds the claim holds; without one, it holds until completed or released.
    lease: int | None = Field(default=None, ge=1, le=7 * 24 * 3600)


@router.post("/tasks")
def add_task(form: TaskForm, key: WriteKey):
    graph = graph_for(key["project_id"])
    try:
        added = memory.add_task(graph, form.id, form.kind, ref=form.about, after=form.after)
    except ValueError:
        reject(422, "A task in after does not exist in this project.")
    usage_event(key["project_id"], "api.task", key["id"])
    return {"id": form.id, "status": "added" if added else "exists"}


@router.post("/tasks/claim")
def claim(form: ClaimForm, key: WriteKey):
    task = memory.claim(graph_for(key["project_id"]), agent(key), form.kind, lease=form.lease)
    usage_event(key["project_id"], "api.task", key["id"])
    return {"data": task}


def owned_task(done, verb: str, task_id: str, key: dict) -> dict:
    changed = done(graph_for(key["project_id"]), agent(key), task_id)
    usage_event(key["project_id"], "api.task", key["id"])
    if not changed:
        reject(409, f"Only the agent that holds this task can {verb} it.")
    return {"id": task_id, "status": "done" if verb == "complete" else "open"}


@router.post("/tasks/{task_id}/complete")
def complete(task_id: TaskId, key: WriteKey):
    return owned_task(memory.complete, "complete", task_id, key)


@router.post("/tasks/{task_id}/release")
def release(task_id: TaskId, key: WriteKey):
    return owned_task(memory.release, "release", task_id, key)


class HandoffForm(BaseModel):
    id: str = Field(pattern=ID)
    to: str = Field(min_length=1, max_length=80)
    points_to: References
    values: dict = Field(default_factory=dict)


@router.post("/handoffs")
def hand_off(form: HandoffForm, key: WriteKey):
    if not is_name(form.to):
        reject(422, "Name the receiving agent as one line of visible text.")
    graph = graph_for(key["project_id"])
    result = memory.hand_off(
        graph, form.id, agent(key), form.to, form.points_to.items(), values=form.values
    )
    usage_event(key["project_id"], "api.handoff", key["id"])
    return receipt(result)


@router.get("/handoffs")
def handoffs(key: ReadKey, waiting: Annotated[bool, Query()] = True):
    found = memory.handoffs_for(graph_for(key["project_id"]), agent(key), waiting_only=waiting)
    usage_event(key["project_id"], "api.handoff.read", key["id"])
    return {"data": found[:100], "limit": 100}


@router.post("/handoffs/{handoff_id}/accept")
def accept(handoff_id: HandoffId, key: WriteKey):
    result = memory.accept(graph_for(key["project_id"]), handoff_id, agent(key))
    usage_event(key["project_id"], "api.handoff", key["id"])
    if result["status"] == "refused":
        reject(403, "This handoff was given to another agent.")
    if result["status"] == "unknown":
        reject(404, "Handoff not found.")
    return result
