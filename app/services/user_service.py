import bcrypt
from bson import ObjectId
from bson.errors import InvalidId
from app.database.client import get_tenant_db, identity_db
from app.utils.datetime_utils import now_brasilia

GENERIC_LISTS_COLLECTION = "generic_lists"
ASSIGNMENT_TYPES = {"text", "number", "select", "multi-select"}


# =========================
# Helpers
# =========================
def validate_object_id(user_id: str):
    try:
        return ObjectId(user_id)
    except InvalidId:
        raise ValueError("Invalid user_id")


def serialize_user(user):
    if not user:
        return user
    out = dict(user)
    out["_id"] = str(out["_id"])
    out.pop("password_hash", None)
    return out


def load_tenant_assignment_map(tenant_database: str) -> dict[str, dict]:
    tenant = identity_db.tenants.find_one(
        {"database": tenant_database},
        {"assignments": 1},
    )
    assignments = (tenant or {}).get("assignments") or []
    out: dict[str, dict] = {}
    for item in assignments:
        if not isinstance(item, dict):
            continue
        key = str(item.get("value", "")).strip()
        ftype = str(item.get("type", "text")).strip().lower()
        if not key or ftype not in ASSIGNMENT_TYPES:
            continue
        out[key] = {
            "type": ftype,
            "list_id": str(item.get("list_id", "")).strip() or None,
        }
    return out


def load_list_allowed_values(db, list_id: str) -> set[str]:
    try:
        oid = ObjectId(list_id)
    except InvalidId:
        raise ValueError("Invalid list_id in assignment configuration")

    linked_list = db[GENERIC_LISTS_COLLECTION].find_one(
        {"_id": oid},
        {"items": 1},
    )
    if not linked_list:
        raise ValueError("Linked generic list not found for assignment")

    values = set()
    for item in linked_list.get("items") or []:
        if not isinstance(item, dict):
            continue
        raw_value = str(item.get("value", "")).strip()
        if raw_value:
            values.add(raw_value)
    return values


def normalize_assignment_value(
    assignment_key: str,
    configured_type: str,
    raw_value,
    allowed_values: set[str] | None,
):
    if configured_type == "text":
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ValueError(f"Assignment '{assignment_key}' requires text value")
        return raw_value.strip()

    if configured_type == "number":
        if isinstance(raw_value, bool):
            raise ValueError(f"Assignment '{assignment_key}' requires numeric value")
        if isinstance(raw_value, (int, float)):
            return float(raw_value)
        if isinstance(raw_value, str):
            cleaned = raw_value.strip().replace(",", ".")
            if not cleaned:
                raise ValueError(f"Assignment '{assignment_key}' requires numeric value")
            try:
                return float(cleaned)
            except ValueError:
                raise ValueError(f"Assignment '{assignment_key}' requires numeric value")
        raise ValueError(f"Assignment '{assignment_key}' requires numeric value")

    if configured_type == "select":
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ValueError(f"Assignment '{assignment_key}' requires a selected value")
        selected = raw_value.strip()
        if allowed_values is not None and selected not in allowed_values:
            raise ValueError(f"Invalid option for assignment '{assignment_key}'")
        return selected

    if configured_type == "multi-select":
        if not isinstance(raw_value, list):
            raise ValueError(f"Assignment '{assignment_key}' requires a list of values")
        normalized_values = []
        seen = set()
        for item in raw_value:
            if not isinstance(item, str):
                raise ValueError(
                    f"Assignment '{assignment_key}' requires string options only"
                )
            selected = item.strip()
            if not selected or selected in seen:
                continue
            if allowed_values is not None and selected not in allowed_values:
                raise ValueError(f"Invalid option for assignment '{assignment_key}'")
            seen.add(selected)
            normalized_values.append(selected)
        if not normalized_values:
            raise ValueError(f"Assignment '{assignment_key}' requires at least one option")
        return normalized_values

    raise ValueError(f"Unsupported assignment type for '{assignment_key}'")


def validate_assignments_payload(db, tenant_database: str, assignments: list):
    if not isinstance(assignments, list):
        raise ValueError("Assignments payload must be a list")

    field_map = load_tenant_assignment_map(tenant_database)
    normalized = []
    seen_keys = set()
    options_cache: dict[str, set[str]] = {}

    for item in assignments:
        if not isinstance(item, dict):
            raise ValueError("Each assignment must be an object")

        assignment_key = str(item.get("type", "")).strip()
        if not assignment_key:
            raise ValueError("Each assignment must include a valid type")
        if assignment_key in seen_keys:
            raise ValueError(f"Duplicate assignment key: {assignment_key}")

        field = field_map.get(assignment_key)
        if not field:
            raise ValueError(f"Assignment key '{assignment_key}' is not configured")

        configured_type = field.get("type")
        list_id = field.get("list_id")
        allowed_values = None
        if configured_type in {"select", "multi-select"}:
            if not list_id:
                raise ValueError(
                    f"Assignment '{assignment_key}' is missing linked list configuration"
                )
            if list_id not in options_cache:
                options_cache[list_id] = load_list_allowed_values(db, list_id)
            allowed_values = options_cache[list_id]

        normalized_value = normalize_assignment_value(
            assignment_key=assignment_key,
            configured_type=configured_type,
            raw_value=item.get("value"),
            allowed_values=allowed_values,
        )
        seen_keys.add(assignment_key)
        normalized.append({"type": assignment_key, "value": normalized_value})

    return normalized


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
    tenant = identity_db.tenants.find_one(
        {"database": tenant_database},
        {"name": 1},
    )
    tenant_name = str((tenant or {}).get("name") or tenant_database)

    user_type = str(user_data.get("type", "")).strip()
    raw_username = (user_data.get("username") or "").strip()
    assignments_payload = validate_assignments_payload(
        db,
        tenant_database,
        user_data.get("assignments", []),
    )

    if user_type == "external":
        username_value = None
    else:
        if not raw_username:
            raise ValueError("Username is required for this account type")
        username_value = raw_username
        if db.users.find_one({"username": username_value}):
            raise ValueError("Username already exists")

    # hash da senha
    password_hash = bcrypt.hashpw(
        user_data["password"].encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")

    user_document = {
        "tenant_id": tenant_name,
        "name": user_data["name"],
        "password_hash": password_hash,
        "email": user_data["email"],
        "phone": user_data.get("phone"),
        "type": user_type,
        "assignments": assignments_payload,
        "active": True,
        "terms": user_data.get("terms", []),
        "created_at": now_brasilia(),
        "updated_at": now_brasilia(),
    }
    user_document["username"] = username_value

    result = db.users.insert_one(user_document)

    user_document["_id"] = str(result.inserted_id)
    user_document.pop("password_hash", None)

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
def update_user(
    tenant_database: str,
    user_id: str,
    user_data: dict,
    actor_user_id: str | None = None,
):

    db = get_tenant_db(tenant_database)
    obj_id = validate_object_id(user_id)

    # 🔒 impedir alteração de campos críticos
    forbidden_fields = ["_id", "password_hash", "tenant_id", "created_at"]
    for field in forbidden_fields:
        user_data.pop(field, None)

    # 🔒 impedir update vazio
    if not user_data:
        raise ValueError("No fields provided for update")

    # 🔒 impedir auto-desativação do próprio usuário autenticado
    if (
        "active" in user_data
        and user_data.get("active") is False
        and actor_user_id
        and str(actor_user_id) == str(user_id)
    ):
        raise ValueError("You cannot deactivate your own account")

    # 🔒 validar username único (se estiver sendo atualizado)
    if "username" in user_data:
        un = user_data.get("username")
        if un is not None and str(un).strip():
            un = str(un).strip()
            user_data["username"] = un
            existing = db.users.find_one(
                {"username": un, "_id": {"$ne": obj_id}}
            )
            if existing:
                raise ValueError("Username already exists")
        else:
            user_data["username"] = None

    if "assignments" in user_data and user_data["assignments"] is not None:
        user_data["assignments"] = validate_assignments_payload(
            db,
            tenant_database,
            user_data["assignments"],
        )

    user_data["updated_at"] = now_brasilia()

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
