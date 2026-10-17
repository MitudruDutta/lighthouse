"""Google authorization-code sign-in shared by both Lighthouse products."""

import hmac
import json
import logging
import os
import secrets
import time
from typing import Annotated
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from fastapi import APIRouter, Depends, Header
from google.auth.transport.requests import Request as GoogleRequest
from google.oauth2.id_token import verify_oauth2_token
from pydantic import BaseModel, Field

from app.memory_api import email_address, rate_limit, reject, signed_in
from app.memory_control import (
    USER_COLUMNS,
    database,
    identifier,
    new_session,
    password_hash,
    public_user,
)

router = APIRouter(prefix="/auth/google")
log = logging.getLogger("lighthouse.auth")


def configuration(redirect_uri):
    client_id = os.environ.get("GOOGLE_CLIENT_ID", "").strip()
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET", "").strip()
    if not client_id or not client_secret:
        reject(503, "Google sign-in is temporarily unavailable. Please try another sign-in method.")
    allowed = {
        os.environ.get("LIGHTHOUSE_APP_URL", "http://localhost:3000").rstrip("/")
        + "/api/auth/google/callback",
        os.environ.get("MEMORY_SITE_URL", "http://localhost:3003").rstrip("/")
        + "/api/auth/google/callback",
    }
    if redirect_uri not in allowed:
        reject(400, "Google sign-in could not be completed. Please start again.")
    return client_id, client_secret


class Start(BaseModel):
    redirect_uri: str = Field(max_length=500)
    state: str = Field(pattern=r"^[A-Za-z0-9_-]{43,128}$")
    nonce: str = Field(pattern=r"^[A-Za-z0-9_-]{43,128}$")
    challenge: str = Field(pattern=r"^[A-Za-z0-9_-]{43}$")


@router.post("/start", dependencies=[Depends(rate_limit)])
def start(form: Start):
    client_id, _ = configuration(form.redirect_uri)
    return {
        "url": "https://accounts.google.com/o/oauth2/v2/auth?"
        + urlencode(
            {
                "client_id": client_id,
                "redirect_uri": form.redirect_uri,
                "response_type": "code",
                "scope": "openid email profile",
                "state": form.state,
                "nonce": form.nonce,
                "code_challenge": form.challenge,
                "code_challenge_method": "S256",
                "prompt": "select_account",
            }
        )
    }


class Exchange(BaseModel):
    redirect_uri: str = Field(max_length=500)
    code: str = Field(min_length=1, max_length=4096)
    verifier: str = Field(pattern=r"^[A-Za-z0-9_-]{43,128}$")
    nonce: str = Field(pattern=r"^[A-Za-z0-9_-]{43,128}$")
    link: bool = False


def google_identity(form, client_id, client_secret):
    request = Request(
        "https://oauth2.googleapis.com/token",
        data=urlencode(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "code": form.code,
                "code_verifier": form.verifier,
                "redirect_uri": form.redirect_uri,
                "grant_type": "authorization_code",
            }
        ).encode(),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urlopen(request, timeout=10) as response:
            body = response.read(65537)
        if len(body) > 65536:
            raise ValueError("Response too large")
        tokens = json.loads(body)
        claims = verify_oauth2_token(tokens["id_token"], GoogleRequest(), client_id)
        if (
            claims.get("email_verified") is not True
            or not isinstance(claims.get("nonce"), str)
            or not hmac.compare_digest(claims["nonce"], form.nonce)
            or not isinstance(claims.get("sub"), str)
            or not 1 <= len(claims["sub"]) <= 255
        ):
            raise ValueError("Identity not verified")
        return claims
    except Exception as exc:  # noqa: BLE001 - every failure is a refusal
        # Provider responses can contain codes and tokens: log only the failure type.
        log.warning("Google identity verification failed: %s", type(exc).__name__)
        reject(401, "Google sign-in could not be completed. Please start again.")


@router.post("/exchange", dependencies=[Depends(rate_limit)])
def exchange(form: Exchange, authorization: Annotated[str | None, Header()] = None):
    client_id, client_secret = configuration(form.redirect_uri)
    linking_user = signed_in(authorization) if form.link else None
    claims = google_identity(form, client_id, client_secret)
    email = email_address(claims.get("email", ""))
    if linking_user and linking_user["email"] != email:
        reject(409, "Choose the Google account with your Lighthouse email address.")
    now = int(time.time())
    with database() as db:
        db.execute("BEGIN IMMEDIATE")
        identity = db.execute(
            "SELECT user_id FROM oauth_identities WHERE provider='google' AND subject=?",
            (claims["sub"],),
        ).fetchone()
        if identity:
            user_id = identity["user_id"]
            if linking_user and linking_user["id"] != user_id:
                reject(409, "This Google account is already connected to another account.")
        else:
            existing = db.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
            # Password accounts have not verified email; never silently merge identities.
            if existing and (not linking_user or linking_user["id"] != existing["id"]):
                reject(
                    409, "Sign in with your password first, then connect Google from your profile."
                )
            user_id = existing["id"] if existing else identifier()
            if not existing:
                name = str(claims.get("name") or email.split("@")[0]).strip()[:80]
                db.execute(
                    "INSERT INTO users(id,email,name,password,created) VALUES (?,?,?,?,?)",
                    (
                        user_id,
                        email,
                        name or "Lighthouse user",
                        password_hash(secrets.token_urlsafe(48)),
                        now,
                    ),
                )
                db.execute(
                    "INSERT INTO workspaces VALUES (?,?,?,?)",
                    (identifier(), user_id, (name or "Lighthouse") + "'s workspace", now),
                )
            db.execute(
                "INSERT INTO oauth_identities VALUES ('google',?,?,?)",
                (claims["sub"], user_id, now),
            )
        token = new_session(db, user_id)
        user = public_user(
            db.execute(f"SELECT {USER_COLUMNS} FROM users u WHERE u.id=?", (user_id,)).fetchone()
        )
    return {"token": token, "user": user}
