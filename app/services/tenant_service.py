from bson import ObjectId
from bson.errors import InvalidId
from datetime import datetime
import bcrypt
import re
import unicodedata

from app.database.client import identity_db, mongo_client


# =========================
# Feature flags (identity.tenants.features)
# =========================
DEFAULT_TENANT_FEATURES = {
    "map": False,
    "mobile": False,
    "public_map": False,
    "sipremo_tools": False,
    "public_trigger": False,
}

DEFAULT_TENANT_ADMIN_PASSWORD = "1234"


def normalize_assignment_fields(raw) -> list:
    """
    Valida e normaliza a configuração de campos de atribuição do tenant.
    Cada item: { "label": str, "value": str, "type": "text" }.
    Por enquanto apenas type=text é aceito.
    """

    if not raw or not isinstance(raw, list):
        return []

    out = []
    seen_values = set()

    for item in raw:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()
        value = str(item.get("value", "")).strip()
        ftype = str(item.get("type", "text")).strip().lower()
        if not label or not value:
            continue
        if ftype != "text":
            continue
        if value in seen_values:
            continue
        seen_values.add(value)
        out.append({"label": label, "value": value, "type": "text"})

    return out


def normalize_tenant_features(raw) -> dict:
    """
    Normaliza o objeto features do Mongo para um dict com todas as chaves booleanas.
    """

    out = dict(DEFAULT_TENANT_FEATURES)
    if not raw or not isinstance(raw, dict):
        return out
    for key in DEFAULT_TENANT_FEATURES:
        out[key] = bool(raw.get(key))
    return out


def slugify_tenant_name(name: str) -> str:
    normalized = unicodedata.normalize("NFD", name or "")
    ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_only).strip("-").lower()
    return slug or "tenant"


def generate_unique_slug_and_database(base_name: str) -> tuple[str, str]:
    base_slug = slugify_tenant_name(base_name)
    attempt = 0

    while True:
        suffix = "" if attempt == 0 else f"-{attempt + 1}"
        candidate = f"{base_slug}{suffix}"
        has_slug = identity_db.tenants.find_one({"slug": candidate}, {"_id": 1})
        has_database = identity_db.tenants.find_one(
            {"database": candidate},
            {"_id": 1},
        )
        if not has_slug and not has_database:
            return candidate, candidate
        attempt += 1


def seed_default_tenant_admin(
    tenant_database: str,
    tenant_name: str,
    tenant_slug: str,
):
    db = mongo_client[tenant_database]
    username = f"user.{tenant_slug}"

    if db.users.find_one({"username": username}, {"_id": 1}):
        return

    now = datetime.utcnow()
    password_hash = bcrypt.hashpw(
        DEFAULT_TENANT_ADMIN_PASSWORD.encode("utf-8"),
        bcrypt.gensalt(),
    ).decode("utf-8")

    db.users.insert_one(
        {
            "tenant_id": tenant_name,
            "name": "Administrador",
            "username": username,
            "password_hash": password_hash,
            "email": f"{username}@tenant.local",
            "phone": None,
            "type": "admin",
            "assignments": [],
            "active": True,
            "terms": [],
            "created_at": now,
            "updated_at": now,
        }
    )


def get_default_admin_username(tenant_slug: str) -> str:
    return f"user.{tenant_slug}"


def serialize_tenant(tenant):
    out = dict(tenant)
    out["_id"] = str(out["_id"])

    database = out.get("database")
    slug = out.get("slug")
    if database:
        db = mongo_client[database]
        out["users_count"] = db.users.count_documents({})
    else:
        out["users_count"] = 0

    if slug:
        out["default_admin_username"] = get_default_admin_username(slug)
    else:
        out["default_admin_username"] = None

    out["default_admin_password"] = DEFAULT_TENANT_ADMIN_PASSWORD
    return out


def resolve_public_tenant_features(host: str | None, tenant_db: str | None) -> dict:
    """
    Resolve features para rotas públicas (sem JWT):
    1) query tenant_db, se informado;
    2) senão, match do Host (sem porta) em tenants.domains;
    3) senão, todas as flags True (compat / dev sem domínio cadastrado).
    """

    tenant = None

    if tenant_db and str(tenant_db).strip():
        tenant = identity_db.tenants.find_one(
            {"database": str(tenant_db).strip(), "active": True},
            {"features": 1},
        )

    if not tenant and host:
        hostname = str(host).split(":")[0].strip().lower()
        if hostname:
            tenant = identity_db.tenants.find_one(
                {"active": True, "domains": hostname},
                {"features": 1},
            )

    if not tenant:
        return {k: True for k in DEFAULT_TENANT_FEATURES}

    return normalize_tenant_features(tenant.get("features"))


# =========================
# Helpers
# =========================
def validate_object_id(tenant_id: str):
    try:
        return ObjectId(tenant_id)
    except InvalidId:
        raise ValueError("Invalid tenant_id")


# =========================
# List Tenants
# =========================
def list_tenants():
    try:
        tenants = list(identity_db.tenants.find({}))
        return [serialize_tenant(t) for t in tenants]
    except Exception as e:
        raise RuntimeError(f"Erro ao listar tenants: {e}")


# =========================
# List tenants for login (public, minimal fields)
# =========================
def list_active_tenants_for_login():
    """
    Retorna apenas tenants ativos com nome e database Mongo
    (o mesmo valor usado em POST /auth/login como tenant_db).
    """

    cursor = identity_db.tenants.find(
        {"active": True},
        {"name": 1, "database": 1, "identity_settings": 1, "terms_settings": 1},
        sort=[("name", 1)],
    )
    out = []
    for doc in cursor:
        db_name = doc.get("database")
        if not db_name:
            continue
        out.append(
            {
                "id": str(doc["_id"]),
                "name": doc.get("name") or db_name,
                "database": db_name,
                "identity_settings": doc.get("identity_settings"),
                "terms_settings": doc.get("terms_settings"),
            }
        )
    return out


# =========================
# Create Tenant
# =========================
def create_tenant(tenant_data: dict):

    for field in ("name",):
        if not tenant_data.get(field):
            raise ValueError(f"Missing required field: {field}")

    name = str(tenant_data["name"]).strip()
    slug, database = generate_unique_slug_and_database(name)

    tenant_document = {
        "name": name,
        "slug": slug,
        "database": database,
        "active": bool(tenant_data.get("active", True)),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    if tenant_data.get("type"):
        tenant_document["type"] = str(tenant_data["type"]).strip()
    if tenant_data.get("cnpj") is not None:
        tenant_document["cnpj"] = str(tenant_data["cnpj"]).strip()
    if tenant_data.get("domains") is not None:
        tenant_document["domains"] = tenant_data["domains"]
    if tenant_data.get("identity_settings"):
        tenant_document["identity_settings"] = str(tenant_data["identity_settings"]).strip()
    if tenant_data.get("terms_settings"):
        tenant_document["terms_settings"] = str(tenant_data["terms_settings"]).strip()
    if tenant_data.get("features") is not None:
        tenant_document["features"] = tenant_data["features"]
    if tenant_data.get("assignments") is not None:
        tenant_document["assignments"] = normalize_assignment_fields(
            tenant_data.get("assignments")
        )

    result = identity_db.tenants.insert_one(tenant_document)

    try:
        seed_default_tenant_admin(
            tenant_database=database,
            tenant_name=name,
            tenant_slug=slug,
        )
    except Exception as e:
        identity_db.tenants.delete_one({"_id": result.inserted_id})
        mongo_client.drop_database(database)
        raise RuntimeError(f"Error creating tenant default admin: {e}")

    tenant_document["_id"] = str(result.inserted_id)

    return tenant_document


# =========================
# Get Tenant by ID
# =========================
def get_tenant_by_id(tenant_id: str):

    obj_id = validate_object_id(tenant_id)

    tenant = identity_db.tenants.find_one({"_id": obj_id})

    if not tenant:
        raise ValueError("Tenant not found")

    return serialize_tenant(tenant)


# =========================
# Update Tenant
# =========================
def update_tenant(
    tenant_id: str,
    tenant_data: dict,
    actor_tenant_database: str | None = None,
):

    obj_id = validate_object_id(tenant_id)
    target_tenant = identity_db.tenants.find_one({"_id": obj_id}, {"database": 1})
    if not target_tenant:
        raise ValueError("Tenant not found")

    forbidden_fields = ["_id", "created_at"]

    for field in forbidden_fields:
        tenant_data.pop(field, None)

    if not tenant_data:
        raise ValueError("No fields provided for update")

    if (
        "active" in tenant_data
        and tenant_data.get("active") is False
        and actor_tenant_database
        and target_tenant.get("database") == actor_tenant_database
    ):
        raise ValueError("You cannot deactivate your own tenant")

    if "assignments" in tenant_data:
        tenant_data["assignments"] = normalize_assignment_fields(
            tenant_data.get("assignments")
        )

    if "slug" in tenant_data and tenant_data["slug"] is not None:
        slug = str(tenant_data["slug"]).strip()
        tenant_data["slug"] = slug
        other = identity_db.tenants.find_one(
            {"slug": slug, "_id": {"$ne": obj_id}},
        )
        if other:
            raise ValueError("Tenant slug already exists")

    if "database" in tenant_data and tenant_data["database"] is not None:
        database = str(tenant_data["database"]).strip()
        tenant_data["database"] = database
        other = identity_db.tenants.find_one(
            {"database": database, "_id": {"$ne": obj_id}},
        )
        if other:
            raise ValueError("Database name already in use")

    if "identity_settings" in tenant_data and tenant_data["identity_settings"] is not None:
        tenant_data["identity_settings"] = str(tenant_data["identity_settings"]).strip()

    if "terms_settings" in tenant_data and tenant_data["terms_settings"] is not None:
        tenant_data["terms_settings"] = str(tenant_data["terms_settings"]).strip()

    tenant_data["updated_at"] = datetime.utcnow()

    result = identity_db.tenants.update_one(
        {"_id": obj_id},
        {"$set": tenant_data},
    )

    if result.matched_count == 0:
        raise ValueError("Tenant not found")

    return get_tenant_by_id(tenant_id)


# =========================
# Delete Tenant
# =========================
def delete_tenant(tenant_id: str, actor_tenant_database: str | None = None):

    obj_id = validate_object_id(tenant_id)

    tenant = identity_db.tenants.find_one({"_id": obj_id}, {"database": 1})

    if not tenant:
        raise ValueError("Tenant not found")

    if actor_tenant_database and tenant.get("database") == actor_tenant_database:
        raise ValueError("You cannot delete your own tenant")

    identity_db.tenants.delete_one({"_id": obj_id})

    return {"message": "Tenant deleted successfully"}
