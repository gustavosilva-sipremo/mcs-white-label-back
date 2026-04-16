from bson import ObjectId
from bson.errors import InvalidId

from app.database.client import get_tenant_db
from app.utils.datetime_utils import now_brasilia

COLLECTION = "generic_lists"
DEFAULT_OPTION_FIELDS = ["label", "value"]
DEFAULT_KEY_FIELD = "value"


def validate_object_id(list_id: str):
    try:
        return ObjectId(list_id)
    except InvalidId:
        raise ValueError("Invalid list_id")


def infer_option_fields(items) -> list[str]:
    if not isinstance(items, list):
        return list(DEFAULT_OPTION_FIELDS)

    for item in items:
        if not isinstance(item, dict):
            continue
        keys = [str(key).strip() for key in item.keys() if str(key).strip()]
        if keys:
            return keys

    return list(DEFAULT_OPTION_FIELDS)


def normalize_option_schema(option_schema, fallback_items=None) -> dict:
    fallback_fields = infer_option_fields(fallback_items)

    if not isinstance(option_schema, dict):
        fields = fallback_fields
        key_field = DEFAULT_KEY_FIELD if DEFAULT_KEY_FIELD in fields else fields[0]
        return {"fields": fields, "key_field": key_field}

    raw_fields = option_schema.get("fields")
    fields = []
    seen_fields = set()
    if isinstance(raw_fields, list):
        for field in raw_fields:
            name = str(field).strip()
            if not name or name in seen_fields:
                continue
            fields.append(name)
            seen_fields.add(name)

    if not fields:
        fields = fallback_fields

    key_field = str(option_schema.get("key_field", "")).strip()
    if not key_field:
        key_field = DEFAULT_KEY_FIELD if DEFAULT_KEY_FIELD in fields else fields[0]
    if key_field not in fields:
        raise ValueError("option_schema.key_field must be present in option_schema.fields")

    return {"fields": fields, "key_field": key_field}


def normalize_items(items, option_schema: dict) -> list:
    if not items:
        return []

    fields = option_schema.get("fields") or list(DEFAULT_OPTION_FIELDS)
    key_field = option_schema.get("key_field") or DEFAULT_KEY_FIELD
    if key_field not in fields:
        raise ValueError("Invalid option schema configuration")

    out = []
    seen_keys = set()
    for item in items:
        if not isinstance(item, dict):
            continue

        normalized_item = {field: str(item.get(field, "")).strip() for field in fields}
        has_any_value = any(normalized_item[field] for field in fields)
        if not has_any_value:
            continue

        missing_fields = [field for field in fields if not normalized_item[field]]
        if missing_fields:
            raise ValueError(
                f"Each item must provide all configured fields: {', '.join(fields)}"
            )

        key_value = normalized_item[key_field]
        if key_value in seen_keys:
            raise ValueError(f"Duplicate item key in field '{key_field}': {key_value}")
        seen_keys.add(key_value)
        out.append(normalized_item)
    return out


def serialize_generic_list(doc: dict) -> dict:
    out = dict(doc)
    out["_id"] = str(out["_id"])
    option_schema = normalize_option_schema(out.get("option_schema"), out.get("items"))
    items = out.get("items") or []
    if not isinstance(items, list):
        items = []
    out["option_schema"] = option_schema
    out["items"] = normalize_items(items, option_schema)
    out["itemsCount"] = len(out["items"])
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

    option_schema = normalize_option_schema(
        data.get("option_schema"),
        data.get("items", []),
    )
    items = normalize_items(data.get("items", []), option_schema)

    doc = {
        "name": name,
        "description": desc,
        "option_schema": option_schema,
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
    current_doc = db[COLLECTION].find_one({"_id": oid})
    if not current_doc:
        raise ValueError("List not found")
    current_schema = normalize_option_schema(
        current_doc.get("option_schema"),
        current_doc.get("items", []),
    )

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

    schema_for_items = current_schema
    if "option_schema" in data:
        schema_for_items = normalize_option_schema(
            data["option_schema"],
            data["items"]
            if "items" in data and data["items"] is not None
            else current_doc.get("items", []),
        )
        data["option_schema"] = schema_for_items

    if "items" in data:
        if data["items"] is None:
            data["items"] = []
        else:
            data["items"] = normalize_items(data["items"], schema_for_items)
    elif "option_schema" in data:
        data["items"] = normalize_items(current_doc.get("items", []), schema_for_items)

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
