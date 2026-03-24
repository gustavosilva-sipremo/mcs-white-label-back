import bcrypt
import secrets
import hashlib
from datetime import datetime, timedelta
from jose import jwt

from app.database.client import get_tenant_db, identity_db
from app.config import (
    JWT_SECRET,
    JWT_ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
)


# =========================
# Helpers
# =========================
def create_access_token(user_id: str, tenant_db: str):
    """
    Gera JWT de acesso
    """

    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)

    payload = {
        "sub": str(user_id),
        "tenant_db": tenant_db,
        "exp": expire,
    }

    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def generate_refresh_token():
    """
    Gera refresh token seguro
    """
    return secrets.token_urlsafe(48)


def hash_refresh_token(token: str):
    """
    Hash SHA256 para refresh token
    """
    return hashlib.sha256(token.encode()).hexdigest()


# =========================
# Login
# =========================
def login_user(data: dict):

    tenant_db = data.get("tenant_db")
    username = data.get("username")
    password = data.get("password")

    if not tenant_db or not username or not password:
        raise ValueError("Missing credentials")

    # conectar tenant
    try:
        db = get_tenant_db(tenant_db)
    except Exception:
        raise ValueError("Invalid tenant")

    user = db.users.find_one(
        {
            "username": username,
            "active": True,
        }
    )

    if not user:
        raise ValueError("Invalid credentials")

    password_hash = user.get("password_hash")

    if not password_hash:
        raise ValueError("Invalid credentials")

    if isinstance(password_hash, str):
        password_hash = password_hash.encode()

    if not bcrypt.checkpw(password.encode(), password_hash):
        raise ValueError("Invalid credentials")

    # =========================
    # gerar tokens
    # =========================

    access_token = create_access_token(user["_id"], tenant_db)

    refresh_token = generate_refresh_token()
    refresh_hash = hash_refresh_token(refresh_token)

    now = datetime.utcnow()
    expires_at = now + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    identity_db.login_tokens.insert_one(
        {
            "user_id": user["_id"],
            "tenant_db": tenant_db,
            "refresh_token_hash": refresh_hash,
            "created_at": now,
            "expires_at": expires_at,
            "revoked": False,
        }
    )

    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


# =========================
# Refresh Access Token
# =========================
def refresh_access_token(refresh_token: str):

    if not refresh_token:
        raise ValueError("Missing refresh token")

    incoming_hash = hash_refresh_token(refresh_token)

    token_doc = identity_db.login_tokens.find_one(
        {
            "refresh_token_hash": incoming_hash,
            "revoked": False,
        }
    )

    if not token_doc:
        raise ValueError("Invalid refresh token")

    if token_doc["expires_at"] < datetime.utcnow():
        raise ValueError("Refresh token expired")

    # =========================
    # ROTATE REFRESH TOKEN
    # =========================

    new_refresh_token = generate_refresh_token()
    new_hash = hash_refresh_token(new_refresh_token)

    identity_db.login_tokens.update_one(
        {"_id": token_doc["_id"]},
        {
            "$set": {
                "refresh_token_hash": new_hash,
                "updated_at": datetime.utcnow(),
            }
        },
    )

    access_token = create_access_token(
        token_doc["user_id"],
        token_doc["tenant_db"],
    )

    return {
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


# =========================
# Logout
# =========================
def logout_user(refresh_token: str):

    if not refresh_token:
        raise ValueError("Missing refresh token")

    token_hash = hash_refresh_token(refresh_token)

    result = identity_db.login_tokens.update_one(
        {
            "refresh_token_hash": token_hash,
            "revoked": False,
        },
        {
            "$set": {
                "revoked": True,
                "revoked_at": datetime.utcnow(),
            }
        },
    )

    if result.matched_count == 0:
        raise ValueError("Invalid refresh token")

    return {"message": "Logged out successfully"}
