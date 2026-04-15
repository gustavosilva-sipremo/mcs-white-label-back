from bson import ObjectId
from bson.errors import InvalidId

from app.database.client import get_tenant_db
from app.utils.datetime_utils import now_brasilia

COLLECTION = "generic_lists"


def validate_object_id(list_id: str):
    try:
        return ObjectId(list_id)
    except InvalidId:
        raise ValueError("Invalid list_id")


def normalize_items(items) -> list:
    if not items:
        return []
    out = []
    seen_values = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label", "")).strip()
        value = str(item.get("value", "")).strip()
        if not label and not value:
            continue
        if not label or not value:
            raise ValueError("Each item must have both label and value")
        if value in seen_values:
            raise ValueError(f"Duplicate item value: {value}")
        seen_values.add(value)
        out.append({"label": label, "value": value})
    return out


def serialize_generic_list(doc: dict) -> dict:
    out = dict(doc)
    out["_id"] = str(out["_id"])
    items = out.get("items") or []
    if not isinstance(items, list):
        items = []
    out["items"] = items
    out["itemsCount"] = len(items)
    return out


def list_generic_lists(tenant_database: str):
    try:
        db = get_tenant_db(tenant_database)
        cursor = db[COLLECTION].find({}).sort("name", 1)
        return [serialize_generic_list(d) for d in cursor]
    except Exception as e:
        raise RuntimeError(f"Erro ao listar listas: {e}")


def create_generic_list(tenant_database: str, data: dict):
    db = get_tenant_db(tenant_database)
    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError("List name is required")

    if db[COLLECTION].find_one({"name": name}):
        raise ValueError("A list with this name already exists")

    desc = data.get("description")
    if desc is not None:
        desc = str(desc).strip() or None

    items = normalize_items(data.get("items", []))

    doc = {
        "name": name,
        "description": desc,
        "items": items,
        "created_at": now_brasilia(),
        "updated_at": now_brasilia(),
    }
    result = db[COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize_generic_list(doc)


def get_generic_list_by_id(tenant_database: str, list_id: str):
    db = get_tenant_db(tenant_database)
    oid = validate_object_id(list_id)
    doc = db[COLLECTION].find_one({"_id": oid})
    if not doc:
        raise ValueError("List not found")
    return serialize_generic_list(doc)


def update_generic_list(tenant_database: str, list_id: str, data: dict):
    db = get_tenant_db(tenant_database)
    oid = validate_object_id(list_id)

    for f in ["_id", "created_at"]:
        data.pop(f, None)

    if "name" in data and data["name"] is not None:
        data["name"] = str(data["name"]).strip()
        if not data["name"]:
            raise ValueError("List name cannot be empty")
        other = db[COLLECTION].find_one(
            {"name": data["name"], "_id": {"$ne": oid}},
        )
        if other:
            raise ValueError("A list with this name already exists")

    if "description" in data:
        if data["description"] is None:
            pass
        else:
            data["description"] = str(data["description"]).strip() or None

    if "items" in data and data["items"] is not None:
        data["items"] = normalize_items(data["items"])

    if not data:
        raise ValueError("No fields provided for update")

    data["updated_at"] = now_brasilia()

    result = db[COLLECTION].update_one({"_id": oid}, {"$set": data})
    if result.matched_count == 0:
        raise ValueError("List not found")

    return get_generic_list_by_id(tenant_database, list_id)


def delete_generic_list(tenant_database: str, list_id: str):
    db = get_tenant_db(tenant_database)
    oid = validate_object_id(list_id)
    res = db[COLLECTION].delete_one({"_id": oid})
    if res.deleted_count == 0:
        raise ValueError("List not found")
    return {"message": "List deleted successfully"}
