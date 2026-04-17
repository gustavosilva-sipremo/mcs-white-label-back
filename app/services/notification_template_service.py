from bson import ObjectId
from bson.errors import InvalidId

from app.database.client import get_tenant_db
from app.utils.datetime_utils import now_brasilia
from app.utils.notification_render import render_preview_bundle

COLLECTION = "notification_templates"


def validate_object_id(tid: str):
    try:
        return ObjectId(tid)
    except InvalidId:
        raise ValueError("Invalid template id")


def serialize_template(doc: dict) -> dict:
    out = dict(doc)
    out["_id"] = str(out["_id"])
    out["channels"] = list(out.get("channels") or [])
    out["header_template"] = str(out.get("header_template") or "")
    out["body_template"] = str(out.get("body_template") or "")
    out["footer_template"] = str(out.get("footer_template") or "")
    return out


def list_notification_templates(tenant_database: str):
    try:
        db = get_tenant_db(tenant_database)
        cursor = db[COLLECTION].find({}).sort([("updated_at", -1), ("name", 1)])
        return [serialize_template(d) for d in cursor]
    except Exception as e:
        raise RuntimeError(f"Erro ao listar templates de notificação: {e}")


def create_notification_template(tenant_database: str, data: dict):
    db = get_tenant_db(tenant_database)
    name = str(data.get("name", "")).strip()
    if not name:
        raise ValueError("Template name is required")

    channels = data.get("channels") or []
    if not isinstance(channels, list) or not channels:
        raise ValueError("At least one channel is required")

    doc = {
        "name": name,
        "channels": channels,
        "header_template": str(data.get("header_template") or ""),
        "body_template": str(data.get("body_template") or ""),
        "footer_template": str(data.get("footer_template") or ""),
        "created_at": now_brasilia(),
        "updated_at": now_brasilia(),
    }
    result = db[COLLECTION].insert_one(doc)
    doc["_id"] = result.inserted_id
    return serialize_template(doc)


def get_notification_template_by_id(tenant_database: str, template_id: str):
    db = get_tenant_db(tenant_database)
    oid = validate_object_id(template_id)
    doc = db[COLLECTION].find_one({"_id": oid})
    if not doc:
        raise ValueError("Template not found")
    return serialize_template(doc)


def update_notification_template(tenant_database: str, template_id: str, data: dict):
    db = get_tenant_db(tenant_database)
    oid = validate_object_id(template_id)
    if not db[COLLECTION].find_one({"_id": oid}):
        raise ValueError("Template not found")

    for f in ["_id", "created_at"]:
        data.pop(f, None)

    if "name" in data and data["name"] is not None:
        data["name"] = str(data["name"]).strip()
        if not data["name"]:
            raise ValueError("Name cannot be empty")

    for key in ("header_template", "body_template", "footer_template"):
        if key in data and data[key] is not None:
            data[key] = str(data[key])

    if "channels" in data:
        ch = data["channels"]
        if not isinstance(ch, list) or not ch:
            raise ValueError("channels cannot be empty")

    if not data:
        raise ValueError("No fields provided for update")

    data["updated_at"] = now_brasilia()

    res = db[COLLECTION].update_one({"_id": oid}, {"$set": data})
    if res.matched_count == 0:
        raise ValueError("Template not found")

    return get_notification_template_by_id(tenant_database, template_id)


def delete_notification_template(tenant_database: str, template_id: str):
    db = get_tenant_db(tenant_database)
    oid = validate_object_id(template_id)
    r = db[COLLECTION].delete_one({"_id": oid})
    if r.deleted_count == 0:
        raise ValueError("Template not found")
    return {"message": "Template deleted successfully"}


def preview_notification_templates(
    header_template: str,
    body_template: str,
    footer_template: str,
    *,
    preview_title: str = "Pré-visualização",
) -> dict:
    return render_preview_bundle(
        header_template,
        body_template,
        footer_template,
        preview_title=preview_title or "Pré-visualização",
    )


def test_pwa_payload(tenant_database: str, template_id: str) -> dict:
    doc = get_notification_template_by_id(tenant_database, template_id)
    if "pwa" not in [c.lower() for c in (doc.get("channels") or [])]:
        raise ValueError("Template does not include the pwa channel")
    bundle = render_preview_bundle(
        doc.get("header_template") or "",
        doc.get("body_template") or "",
        doc.get("footer_template") or "",
        preview_title=doc.get("name") or "Notificação",
    )
    pwa = bundle.get("pwa") or {}
    return {
        "template_id": str(doc["_id"]),
        "title": str(pwa.get("title") or doc.get("name") or "Notificação"),
        "body": str(pwa.get("body") or ""),
    }
