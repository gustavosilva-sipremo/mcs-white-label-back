import bcrypt
from bson import ObjectId
from bson.errors import InvalidId
from datetime import datetime
from app.database.client import get_tenant_db


# =========================
# Helpers
# =========================
def validate_object_id(user_id: str):
    try:
        return ObjectId(user_id)
    except InvalidId:
        raise ValueError("Invalid user_id")


def serialize_user(user):
    user["_id"] = str(user["_id"])
    return user


# =========================
# List Users
# =========================
def list_users(tenant_database: str):
    try:
        db = get_tenant_db(tenant_database)
        users = list(db.users.find({}))
        return [serialize_user(user) for user in users]
    except Exception as e:
        raise RuntimeError(f"Erro ao listar usuários: {e}")


# =========================
# Create User
# =========================
def create_user(tenant_database: str, user_data: dict):

    db = get_tenant_db(tenant_database)

    # 🔒 validar username único
    if db.users.find_one({"username": user_data["username"]}):
        raise ValueError("Username already exists")

    # hash da senha
    password_hash = bcrypt.hashpw(
        user_data["password"].encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")

    user_document = {
        "tenant_id": tenant_database,
        "name": user_data["name"],
        "username": user_data["username"],
        "password_hash": password_hash,
        "email": user_data["email"],
        "phone": user_data.get("phone"),
        "type": user_data["type"],
        "assignments": user_data.get("assignments", []),
        "teams": user_data.get("teams", []),
        "active": True,
        "terms": user_data.get("terms", []),
        "created_at": datetime.utcnow(),
        "updated_at": datetime.utcnow(),
    }

    result = db.users.insert_one(user_document)

    user_document["_id"] = str(result.inserted_id)

    return user_document


# =========================
# Get User by ID
# =========================
def get_user_by_id(tenant_database: str, user_id: str):

    db = get_tenant_db(tenant_database)
    obj_id = validate_object_id(user_id)

    user = db.users.find_one({"_id": obj_id})

    if not user:
        raise ValueError("User not found")

    return serialize_user(user)


# =========================
# Update User
# =========================
def update_user(tenant_database: str, user_id: str, user_data: dict):

    db = get_tenant_db(tenant_database)
    obj_id = validate_object_id(user_id)

    # 🔒 impedir alteração de campos críticos
    forbidden_fields = ["_id", "password_hash", "tenant_id", "created_at"]
    for field in forbidden_fields:
        user_data.pop(field, None)

    # 🔒 impedir update vazio
    if not user_data:
        raise ValueError("No fields provided for update")

    # 🔒 validar username único (se estiver sendo atualizado)
    if "username" in user_data:
        existing = db.users.find_one(
            {"username": user_data["username"], "_id": {"$ne": obj_id}}
        )
        if existing:
            raise ValueError("Username already exists")

    user_data["updated_at"] = datetime.utcnow()

    result = db.users.update_one({"_id": obj_id}, {"$set": user_data})

    if result.matched_count == 0:
        raise ValueError("User not found")

    return get_user_by_id(tenant_database, user_id)


# =========================
# Delete User
# =========================
def delete_user(tenant_database: str, user_id: str):

    db = get_tenant_db(tenant_database)
    obj_id = validate_object_id(user_id)

    # 🔒 verificar se usuário existe antes
    user = db.users.find_one({"_id": obj_id})
    if not user:
        raise ValueError("User not found")

    db.users.delete_one({"_id": obj_id})

    return {"message": "User deleted successfully"}
