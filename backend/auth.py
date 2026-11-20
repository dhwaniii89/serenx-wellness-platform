"""Password hashing and token sessions (standard library only)."""
import hashlib
import hmac
import secrets

from fastapi import Depends, Header, HTTPException

from . import db


def hash_password(password: str, salt: str | None = None) -> tuple[str, str]:
    salt = salt or secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000)
    return h.hex(), salt


def verify_password(password: str, pw_hash: str, salt: str) -> bool:
    return hmac.compare_digest(hash_password(password, salt)[0], pw_hash)


def create_token(user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    db.ex(
        "INSERT INTO sessions (token, user_id, created_at) VALUES (?,?,?)",
        (token, user_id, db.now()),
    )
    return token


def current_user(authorization: str = Header(default="")) -> dict:
    token = authorization.removeprefix("Bearer ").strip()
    rows = db.q(
        "SELECT u.* FROM sessions s JOIN users u ON u.id = s.user_id WHERE s.token = ?",
        (token,),
    )
    if not rows:
        raise HTTPException(401, "Please log in again.")
    return rows[0]


def doctor_only(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "doctor":
        raise HTTPException(403, "Doctors only.")
    return user


def patient_only(user: dict = Depends(current_user)) -> dict:
    if user["role"] != "patient":
        raise HTTPException(403, "Patients only.")
    return user
