from bson import ObjectId
from bson.errors import InvalidId
from datetime import datetime

from app.database.client import identity_db


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


def serialize_tenant(tenant):
    tenant["_id"] = str(tenant["_id"])
    return tenant


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
        {"name": 1, "database": 1, "identity_settings": 1},
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
            }
        )
    return out


# =========================
# Create Tenant
# =========================
def create_tenant(tenant_data: dict):

    for field in ("name", "slug", "database"):
        if not tenant_data.get(field):
            raise ValueError(f"Missing required field: {field}")

    slug = str(tenant_data["slug"]).strip()
    database = str(tenant_data["database"]).strip()
    name = str(tenant_data["name"]).strip()

    if identity_db.tenants.find_one({"slug": slug}):
        raise ValueError("Tenant slug already exists")
    if identity_db.tenants.find_one({"database": database}):
        raise ValueError("Database name already in use")

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
    if tenant_data.get("features") is not None:
        tenant_document["features"] = tenant_data["features"]

    result = identity_db.tenants.insert_one(tenant_document)

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
def update_tenant(tenant_id: str, tenant_data: dict):

    obj_id = validate_object_id(tenant_id)

    forbidden_fields = ["_id", "created_at"]

    for field in forbidden_fields:
        tenant_data.pop(field, None)

    if not tenant_data:
        raise ValueError("No fields provided for update")

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
def delete_tenant(tenant_id: str):

    obj_id = validate_object_id(tenant_id)

    tenant = identity_db.tenants.find_one({"_id": obj_id})

    if not tenant:
        raise ValueError("Tenant not found")

    identity_db.tenants.delete_one({"_id": obj_id})

    return {"message": "Tenant deleted successfully"}
