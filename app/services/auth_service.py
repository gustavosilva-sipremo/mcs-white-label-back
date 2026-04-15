import bcrypt
from datetime import datetime, timedelta
from jose import jwt, JWTError
from bson import ObjectId
from bson.errors import InvalidId

from app.database.client import get_tenant_db, identity_db
from app.config import (
    JWT_SECRET,
    REFRESH_JWT_SECRET,
    JWT_ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES,
    REFRESH_TOKEN_EXPIRE_DAYS,
)

REFRESH_TOKEN_TYP = "refresh"


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


def create_refresh_token(user_id: str, tenant_db: str):
    """
    Gera JWT de refresh (stateless, sem persistência em banco).
    """

    expire = datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

    payload = {
        "sub": str(user_id),
        "tenant_db": tenant_db,
        "typ": REFRESH_TOKEN_TYP,
        "exp": expire,
    }

    return jwt.encode(payload, REFRESH_JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_refresh_token_payload(refresh_token: str) -> dict:
    """
    Valida assinatura e exp do refresh JWT.
    """

    try:
        payload = jwt.decode(
            refresh_token,
            REFRESH_JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
        )
    except JWTError:
        raise ValueError("Invalid refresh token")

    if payload.get("typ") != REFRESH_TOKEN_TYP:
        raise ValueError("Invalid refresh token")

    return payload


# =========================
# Login
# =========================
def login_user(data: dict):

    tenant_db = data.get("tenant_db")
    username = data.get("username")
    password = data.get("password")

    if not tenant_db or not username or not password:
        raise ValueError("Missing credentials")

    tenant = identity_db.tenants.find_one(
        {"database": tenant_db},
        {"active": 1},
    )
    if not tenant:
        raise ValueError("Invalid tenant")
    if tenant.get("active") is not True:
        raise ValueError("Tenant is inactive")

    # conectar tenant
    try:
        db = get_tenant_db(tenant_db)
    except Exception:
        raise ValueError("Invalid tenant")

    user = db.users.find_one({"username": username})

    if not user:
        raise ValueError("Invalid credentials")

    if user.get("active") is not True:
        raise ValueError("User is inactive")

    password_hash = user.get("password_hash")

    if not password_hash:
        raise ValueError("Invalid credentials")

    if isinstance(password_hash, str):
        password_hash = password_hash.encode()

    if not bcrypt.checkpw(password.encode(), password_hash):
        raise ValueError("Invalid credentials")

    access_token = create_access_token(user["_id"], tenant_db)
    refresh_token = create_refresh_token(user["_id"], tenant_db)

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

    payload = decode_refresh_token_payload(refresh_token)

    user_id = payload.get("sub")
    tenant_db = payload.get("tenant_db")

    if not user_id or not tenant_db:
        raise ValueError("Invalid refresh token")

    access_token = create_access_token(user_id, tenant_db)

    # Sem rotação: o mesmo refresh JWT permanece válido até expirar.
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": "bearer",
        "expires_in": ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    }


# =========================
# Logout
# =========================
def logout_user(_refresh_token: str | None = None):
    """
    Stateless: não há revogação no servidor. O cliente descarta os tokens.
    """

    return {"message": "Logged out successfully"}


def normalize_term_key(value: str) -> str:
    normalized = value.strip().lower()
    normalized = normalized.replace(" ", "")
    if normalized.startswith("termos"):
        normalized = normalized[len("termos") :]
    if normalized.startswith("termo"):
        normalized = normalized[len("termo") :]
    return normalized


def update_logged_user_terms(
    tenant_db: str,
    user_id: str,
    terms: list[dict],
    required_term_names: list[str] | None = None,
):
    if not tenant_db or not user_id:
        raise ValueError("Invalid authenticated user")

    if not isinstance(terms, list) or len(terms) == 0:
        raise ValueError("Terms payload is required")

    normalized_terms = []
    accepted_map: dict[str, bool] = {}

    for item in terms:
        name = item.get("name") if isinstance(item, dict) else None
        value = item.get("value") if isinstance(item, dict) else None

        if not isinstance(name, str) or not name.strip():
            raise ValueError("Each term must include a valid name")
        if not isinstance(value, bool):
            raise ValueError("Each term must include a boolean value")

        normalized_terms.append({"name": name.strip(), "value": value})
        accepted_map[normalize_term_key(name)] = value

    required_term_names = required_term_names or []
    for required_name in required_term_names:
        key = normalize_term_key(required_name)
        if not key:
            continue
        if accepted_map.get(key) is not True:
            raise ValueError(f"Required term '{required_name}' must be accepted")

    try:
        obj_user_id = ObjectId(user_id)
    except InvalidId:
        raise ValueError("Invalid user id")

    db = get_tenant_db(tenant_db)
    result = db.users.update_one(
        {"_id": obj_user_id},
        {
            "$set": {
                "terms": normalized_terms,
                "updated_at": datetime.utcnow(),
            }
        },
    )

    if result.matched_count == 0:
        raise ValueError("User not found")

    user = db.users.find_one({"_id": obj_user_id})
    if not user:
        raise ValueError("User not found")

    user["_id"] = str(user["_id"])
    user.pop("password_hash", None)
    return user
