"""Workspaces and projects of a Memory account: create, rename, and delete.

Deleting a project deletes its graph, its keys, and its usage records. Deleting a
workspace deletes its projects. Each delete names what it deletes, so a request sent by
mistake, or by a script with the wrong id, deletes nothing.
"""

import logging
import time

from fastapi import APIRouter
from pydantic import BaseModel, Field
from redis.exceptions import ResponseError

from app.db import get_db
from app.memory_api import User, owned_project, reject
from app.memory_control import database, identifier

router = APIRouter(prefix="/console")
log = logging.getLogger("lighthouse.memory")
WORKSPACES = 5  # for one account


class Named(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class ProjectChange(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=400)


class Confirm(BaseModel):
    # The name of what is deleted, typed by the person deleting it.
    confirm: str = Field(max_length=80)


def name_of(form: Named) -> str:
    name = form.name.strip()
    if not name:
        reject(422, "Enter a name.")
    return name


def owned_workspace(db, user: dict, workspace_id: str) -> dict:
    found = db.execute(
        "SELECT * FROM workspaces WHERE id=? AND owner=?", (workspace_id, user["id"])
    ).fetchone()
    if not found:
        reject(404, "Workspace not found.")
    return dict(found)


def drop_project(db, project_id: str):
    """The graph first: if FalkorDB cannot delete it, the project stays, and so does the
    way to try again."""
    try:
        get_db().select_graph("memory_" + project_id).delete()
    except ResponseError as exc:
        if "empty key" not in str(exc):
            raise
    keys = [
        row[0] for row in db.execute("SELECT id FROM api_keys WHERE project_id=?", (project_id,))
    ]
    db.executemany("DELETE FROM key_limits WHERE key_id=?", [(key,) for key in keys])
    db.execute("DELETE FROM api_keys WHERE project_id=?", (project_id,))
    db.execute("DELETE FROM usage WHERE project_id=?", (project_id,))
    db.execute("DELETE FROM projects WHERE id=?", (project_id,))


@router.post("/workspaces")
def create_workspace(form: Named, user: User):
    name = name_of(form)
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        held = db.execute("SELECT count(*) FROM workspaces WHERE owner=?", (user["id"],))
        if held.fetchone()[0] >= WORKSPACES:
            reject(409, f"An account can have up to {WORKSPACES} workspaces.")
        workspace_id, now = identifier(), int(time.time())
        db.execute("INSERT INTO workspaces VALUES (?,?,?,?)", (workspace_id, user["id"], name, now))
    return {"id": workspace_id, "name": name, "created": now}


@router.patch("/workspaces/{workspace_id}")
def rename_workspace(workspace_id: str, form: Named, user: User):
    name = name_of(form)
    with database() as db:
        found = owned_workspace(db, user, workspace_id)
        db.execute("UPDATE workspaces SET name=? WHERE id=?", (name, workspace_id))
    return found | {"name": name}


@router.delete("/workspaces/{workspace_id}")
def delete_workspace(workspace_id: str, form: Confirm, user: User):
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        found = owned_workspace(db, user, workspace_id)
        if form.confirm != found["name"]:
            reject(422, "Type the workspace name to delete it.")
        if (
            db.execute("SELECT count(*) FROM workspaces WHERE owner=?", (user["id"],)).fetchone()[0]
            < 2
        ):
            reject(409, "Your only workspace cannot be deleted.")
        projects = [
            row[0]
            for row in db.execute("SELECT id FROM projects WHERE workspace_id=?", (workspace_id,))
        ]
        for project_id in projects:
            drop_project(db, project_id)
        db.execute("DELETE FROM workspaces WHERE id=?", (workspace_id,))
    log.info("Workspace deleted with %d projects", len(projects))
    return {"deleted": True, "projects": len(projects)}


@router.patch("/projects/{project_id}")
def change_project(project_id: str, form: ProjectChange, user: User):
    found = owned_project(user, project_id)
    name = found["name"] if form.name is None else form.name.strip()
    description = found["description"] if form.description is None else form.description.strip()
    if not name:
        reject(422, "Enter a project name.")
    with database() as db:
        db.execute(
            "UPDATE projects SET name=?,description=? WHERE id=?", (name, description, project_id)
        )
    return found | {"name": name, "description": description}


@router.delete("/projects/{project_id}")
def delete_project(project_id: str, form: Confirm, user: User):
    found = owned_project(user, project_id)
    if form.confirm != found["name"]:
        reject(422, "Type the project name to delete it.")
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        drop_project(db, project_id)
    return {"deleted": True}
