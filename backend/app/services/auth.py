import hmac
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from jose import JWTError, jwt
from dotenv import load_dotenv


ALGORITHM = "HS256"
AUTH_ENV_PATH = Path(__file__).resolve().parents[3] / "backend" / ".env"


def _required_setting(name: str) -> str:
    load_dotenv(AUTH_ENV_PATH)
    value = os.getenv(name, "")

    if not value or not value.strip():
        raise RuntimeError(f"{name} is not configured.")

    return value


def authenticate(username: str, password: str) -> str | None:
    configured_username = _required_setting("REVIEWER_USERNAME")
    configured_password = _required_setting("REVIEWER_PASSWORD")

    username_matches = hmac.compare_digest(
        username.encode("utf-8"),
        configured_username.encode("utf-8"),
    )
    password_matches = hmac.compare_digest(
        password.encode("utf-8"),
        configured_password.encode("utf-8"),
    )

    if not (username_matches and password_matches):
        return None

    secret = _required_setting("JWT_SECRET_KEY")

    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET_KEY must be at least 32 characters.")

    try:
        expires_in = int(os.getenv("JWT_ACCESS_TOKEN_MINUTES", "60"))
    except ValueError as exc:
        raise RuntimeError(
            "JWT_ACCESS_TOKEN_MINUTES must be a positive integer."
        ) from exc

    if expires_in <= 0:
        raise RuntimeError(
            "JWT_ACCESS_TOKEN_MINUTES must be a positive integer."
        )

    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=expires_in
    )
    return jwt.encode(
        {"sub": configured_username, "exp": expires_at},
        secret,
        algorithm=ALGORITHM,
    )


def validate_access_token(token: str) -> str | None:
    secret = _required_setting("JWT_SECRET_KEY")

    if len(secret) < 32:
        raise RuntimeError("JWT_SECRET_KEY must be at least 32 characters.")

    try:
        payload = jwt.decode(token, secret, algorithms=[ALGORITHM])
    except JWTError:
        return None

    subject = payload.get("sub")
    return subject if isinstance(subject, str) and subject else None


def get_access_token_lifetime() -> int:
    try:
        minutes = int(os.getenv("JWT_ACCESS_TOKEN_MINUTES", "60"))
    except ValueError as exc:
        raise RuntimeError(
            "JWT_ACCESS_TOKEN_MINUTES must be a positive integer."
        ) from exc

    if minutes <= 0:
        raise RuntimeError(
            "JWT_ACCESS_TOKEN_MINUTES must be a positive integer."
        )

    return minutes * 60
