"""Account entry points shared by the operations and Memory products."""

from fastapi import APIRouter, Depends

from app import memory_api
from app.memory_control import database

router = APIRouter(prefix="/api/auth")
router.add_api_route(
    "/register",
    memory_api.register,
    methods=["POST"],
    dependencies=[Depends(memory_api.rate_limit)],
)
router.add_api_route(
    "/login", memory_api.login, methods=["POST"], dependencies=[Depends(memory_api.rate_limit)]
)
router.add_api_route("/logout", memory_api.logout, methods=["POST"])


def workspace_for(user):
    with database() as db:
        row = db.execute(
            "SELECT id FROM workspaces WHERE owner=? ORDER BY created,id LIMIT 1", (user["id"],)
        ).fetchone()
    if not row:
        memory_api.reject(403, "Workspace access is required.")
    return row["id"]


@router.get("/me")
def me(user: memory_api.User):
    return {"user": user, "workspace": workspace_for(user)}
