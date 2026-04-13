from bson import ObjectId
from bson.errors import InvalidId
from datetime import datetime

from app.database.client import identity_db


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

    # validar slug único
    if identity_db.tenants.find_one({"slug": tenant_data["slug"]}):
        raise ValueError("Tenant slug already exists")

    tenant_document = {
        "name": tenant_data["name"],
        "slug": tenant_data["slug"],  # usado na URL
        "database": tenant_data["database"],  # nome do banco Mongo
        "active": True,
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

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
