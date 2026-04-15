from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from jose import jwt, JWTError
from bson import ObjectId
from bson.errors import InvalidId

from app.config import JWT_SECRET, JWT_ALGORITHM
from app.database.client import get_tenant_db, identity_db
from app.services.tenant_service import normalize_tenant_features


# =========================
# Security scheme
# =========================
security = HTTPBearer(auto_error=False)


# =========================
# Decode JWT
# =========================
def decode_token(token: str) -> dict:
    """
    Decodifica o JWT e retorna o payload
    """

    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
        )
        return payload

    except JWTError:
        raise HTTPException(
            status_code=401,
            detail="Invalid or expired token",
        )


# =========================
# Get current authenticated user
# =========================
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    """
    Valida o JWT e retorna o usuário autenticado
    """

    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Authorization header missing",
        )

    token = credentials.credentials

    payload = decode_token(token)

    user_id = payload.get("sub")
    tenant_db = payload.get("tenant_db")

    if not user_id or not tenant_db:
        raise HTTPException(
            status_code=401,
            detail="Invalid token payload",
        )

    # validar ObjectId
    try:
        user_object_id = ObjectId(user_id)
    except InvalidId:
        raise HTTPException(
            status_code=401,
            detail="Invalid user id",
        )

    # conectar ao tenant
    try:
        db = get_tenant_db(tenant_db)
    except Exception:
        raise HTTPException(
            status_code=401,
            detail="Invalid tenant",
        )

    # buscar usuário
    user = db.users.find_one(
        {
            "_id": user_object_id,
            "active": True,
        }
    )

    if not user:
        raise HTTPException(
            status_code=401,
            detail="User not found or inactive",
        )

    # serializar ObjectId
    user["_id"] = str(user["_id"])

    # remover dados sensíveis
    user.pop("password_hash", None)

    # branding / white-label: caminho do JSON em public/ (ex.: /documents/identities/id-sipremo.json)
    tenant = identity_db.tenants.find_one(
        {"database": tenant_db},
        {
            "identity_settings": 1,
            "terms_settings": 1,
            "name": 1,
            "features": 1,
            "assignments": 1,
        },
    )
    if tenant:
        user["identity_settings"] = tenant.get("identity_settings")
        user["terms_settings"] = tenant.get("terms_settings")
        user["tenant_name"] = tenant.get("name")
        user["features"] = normalize_tenant_features(tenant.get("features"))
        user["assignment_fields"] = tenant.get("assignments") or []
    else:
        user["identity_settings"] = None
        user["terms_settings"] = None
        user["tenant_name"] = None
        user["features"] = normalize_tenant_features(None)
        user["assignment_fields"] = []

    user["tenant_database"] = tenant_db

    return user


# =========================
# Admin dependency
# =========================
def get_admin_user(
    current_user: dict = Depends(get_current_user),
):
    """
    Permite apenas usuários admin
    """

    if current_user.get("type") != "admin":
        raise HTTPException(
            status_code=403,
            detail="Admin privileges required",
        )

    return current_user


# =========================
# Admin + tenant path guard
# =========================
def require_admin_same_tenant(
    tenant_database: str,
    admin_user: dict = Depends(get_admin_user),
):
    """
    Garante que o tenant da URL é o mesmo do JWT (usuário admin do tenant).
    Impede que um admin liste ou altere usuários de outro tenant.
    """

    if tenant_database != admin_user.get("tenant_database"):
        raise HTTPException(
            status_code=403,
            detail="Tenant access denied",
        )

    return admin_user
