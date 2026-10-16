"""Persistent account/project control plane, separate from application data and graphs."""

import hashlib
import hmac
import json
import os
from pathlib import Path
import secrets
import sqlite3
import time
from contextlib import contextmanager

USER_COLUMNS = "u.*, EXISTS(SELECT 1 FROM oauth_identities oi WHERE oi.provider='google' AND oi.user_id=u.id) AS google_connected"

SCHEMA = """
CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,email TEXT NOT NULL UNIQUE,name TEXT NOT NULL,password TEXT NOT NULL,created INTEGER NOT NULL,timezone TEXT NOT NULL DEFAULT 'UTC');
CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),expires INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS oauth_identities(provider TEXT NOT NULL,subject TEXT NOT NULL,user_id TEXT NOT NULL REFERENCES users(id),created INTEGER NOT NULL,PRIMARY KEY(provider,subject),UNIQUE(provider,user_id));
CREATE TABLE IF NOT EXISTS workspaces(id TEXT PRIMARY KEY,owner TEXT NOT NULL REFERENCES users(id),name TEXT NOT NULL,created INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS projects(id TEXT PRIMARY KEY,workspace_id TEXT NOT NULL REFERENCES workspaces(id),name TEXT NOT NULL,description TEXT NOT NULL DEFAULT '',created INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS api_keys(id TEXT PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id),hash TEXT NOT NULL UNIQUE,prefix TEXT NOT NULL,name TEXT NOT NULL,scopes TEXT NOT NULL,created INTEGER NOT NULL,expires INTEGER NOT NULL,revoked INTEGER,last_used INTEGER);
CREATE TABLE IF NOT EXISTS usage(id INTEGER PRIMARY KEY,project_id TEXT NOT NULL REFERENCES projects(id),key_id TEXT,operation TEXT NOT NULL,status INTEGER NOT NULL,at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS usage_project ON usage(project_id,at);
CREATE TABLE IF NOT EXISTS key_limits(key_id TEXT PRIMARY KEY REFERENCES api_keys(id),window INTEGER NOT NULL,count INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS attempts(ip TEXT NOT NULL,at INTEGER NOT NULL);
CREATE INDEX IF NOT EXISTS attempts_ip ON attempts(ip,at);
"""


@contextmanager
def database():
    path = Path(os.environ.get("LIGHTHOUSE_MEMORY_CONTROL_DB", "/data/memory-control.sqlite3"))
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=15)
    os.chmod(path, 0o600)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=WAL")
    connection.executescript(SCHEMA)
    try:
        with connection:
            yield connection
    finally:
        connection.close()
    os.chmod(path, 0o600)


def identifier() -> str:
    return secrets.token_hex(16)


def digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def password_hash(password: str, salt: str | None = None) -> str:
    salt = salt or secrets.token_hex(16)
    value = hashlib.scrypt(
        password.encode(), salt=bytes.fromhex(salt), n=32768, r=8, p=3, maxmem=67108864
    ).hex()
    return f"{salt}:{value}"


def check_password(password: str, stored: str) -> bool:
    salt = stored.split(":")[0]
    return hmac.compare_digest(password_hash(password, salt), stored)


DUMMY_PASSWORD = password_hash("not-a-real-account-password", "00" * 16)


def new_session(db, user: str) -> str:
    token = "lhs_" + secrets.token_urlsafe(32)
    db.execute("DELETE FROM sessions WHERE expires < ?", (int(time.time()),))
    db.execute(
        "INSERT INTO sessions VALUES (?,?,?)", (digest(token), user, int(time.time()) + 604800)
    )
    return token


def public_user(row) -> dict:
    return {key: row[key] for key in ("id", "email", "name", "timezone", "created")} | {
        "google_connected": bool(row["google_connected"])
        if "google_connected" in row.keys()
        else False
    }


def issue_key(db, project: str, name: str, scopes: list[str], days: int) -> dict:
    token = "lhm_" + secrets.token_urlsafe(32)
    key_id, now = identifier(), int(time.time())
    db.execute(
        "INSERT INTO api_keys(id,project_id,hash,prefix,name,scopes,created,expires) VALUES (?,?,?,?,?,?,?,?)",
        (
            key_id,
            project,
            digest(token),
            token[:12],
            name,
            json.dumps(scopes),
            now,
            now + days * 86400,
        ),
    )
    return {
        "id": key_id,
        "secret": token,
        "name": name,
        "prefix": token[:12],
        "scopes": scopes,
        "expires": now + days * 86400,
    }
