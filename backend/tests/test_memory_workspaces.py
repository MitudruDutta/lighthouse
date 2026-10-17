"""Workspaces and projects: create, rename, delete, and what a delete takes with it."""

from app.memory_control import database
from tests.test_memory_product import account, client, key, project  # noqa: F401


def graphs(db):
    return set(db.list_graphs())


def test_a_deleted_project_takes_its_graph_keys_and_usage(client, db):  # noqa: F811
    owner, data = account(client)
    pid = project(client, owner, data)
    agent, _ = key(client, owner, pid)
    fact = {"key": "a", "title": "A", "text": "kept until the project goes"}
    assert client.post("/v1/memories", headers=agent, json=fact).status_code == 200
    assert "memory_" + pid in graphs(db)

    renamed = client.patch(f"/console/projects/{pid}", headers=owner, json={"name": "Renamed"})
    assert renamed.json()["name"] == "Renamed" and renamed.json()["description"] == ""

    wrong = client.request(
        "DELETE", f"/console/projects/{pid}", headers=owner, json={"confirm": "x"}
    )
    assert wrong.status_code == 422 and "memory_" + pid in graphs(db)
    stranger, _ = account(client, "Stranger")
    theirs = client.request(
        "DELETE", f"/console/projects/{pid}", headers=stranger, json={"confirm": "Renamed"}
    )
    assert theirs.status_code == 404

    gone = client.request(
        "DELETE", f"/console/projects/{pid}", headers=owner, json={"confirm": "Renamed"}
    )
    assert gone.json() == {"deleted": True}
    assert "memory_" + pid not in graphs(db)
    assert client.get("/v1/memories", headers=agent).status_code == 401
    with database() as control:
        for table, column in (
            ("projects", "id"),
            ("api_keys", "project_id"),
            ("usage", "project_id"),
        ):
            rows = control.execute(f"SELECT count(*) FROM {table} WHERE {column}=?", (pid,))
            assert rows.fetchone()[0] == 0, table
    assert client.get("/console/overview", headers=owner).json()["projects"] == []


def test_workspaces_are_created_renamed_and_deleted_with_their_projects(client, db):  # noqa: F811
    owner, data = account(client)
    (first,) = data["workspaces"]
    only = client.request(
        "DELETE",
        f"/console/workspaces/{first['id']}",
        headers=owner,
        json={"confirm": first["name"]},
    )
    assert only.status_code == 409

    made = client.post("/console/workspaces", headers=owner, json={"name": "  Team  "}).json()
    assert made["name"] == "Team"
    assert client.post("/console/workspaces", headers=owner, json={"name": " "}).status_code == 422
    response = client.post(
        "/console/projects", headers=owner, json={"workspace_id": made["id"], "name": "Inside"}
    )
    inside = response.json()["id"]
    renamed = client.patch(
        f"/console/workspaces/{made['id']}", headers=owner, json={"name": "Crew"}
    )
    assert renamed.json()["name"] == "Crew"

    stranger, _ = account(client, "Stranger")
    assert (
        client.patch(
            f"/console/workspaces/{made['id']}", headers=stranger, json={"name": "Mine"}
        ).status_code
        == 404
    )
    assert (
        client.post(
            "/console/projects", headers=stranger, json={"workspace_id": made["id"], "name": "x"}
        ).status_code
        == 404
    )

    deleted = client.request(
        "DELETE", f"/console/workspaces/{made['id']}", headers=owner, json={"confirm": "Crew"}
    )
    assert deleted.json() == {"deleted": True, "projects": 1}
    assert "memory_" + inside not in graphs(db)
    overview = client.get("/console/overview", headers=owner).json()
    assert [item["id"] for item in overview["workspaces"]] == [first["id"]]

    for number in range(4):
        client.post("/console/workspaces", headers=owner, json={"name": f"W{number}"})
    full = client.post("/console/workspaces", headers=owner, json={"name": "One more"})
    assert full.status_code == 409
