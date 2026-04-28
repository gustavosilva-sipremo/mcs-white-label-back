from bson import ObjectId
from bson.errors import InvalidId

from app.database.client import get_tenant_db
from app.utils.datetime_utils import now_brasilia
from app.utils.notification_render import render_preview_bundle

COLLECTION = "notification_templates"
SUBTEMPLATE_KEYS = ("header_template", "body_template", "footer_template")


def validate_object_id(tid: str):
    try:
        return ObjectId(tid)
    except InvalidId:
        raise ValueError("Invalid template id")


def _sanitize_channels(channels: list) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for c in channels or []:
        s = str(c).strip().lower()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def _normalize_single_channel(payload: dict | None) -> dict[str, str]:
    source = payload or {}
    return {key: str(source.get(key) or "") for key in SUBTEMPLATE_KEYS}


def _build_channel_templates(data: dict, channels: list[str]) -> dict[str, dict[str, str]]:
    raw = data.get("channel_templates") or {}
    out: dict[str, dict[str, str]] = {}
    for channel in channels:
        if isinstance(raw, dict) and isinstance(raw.get(channel), dict):
            out[channel] = _normalize_single_channel(raw.get(channel))
            continue

        # Fallback legado: principal e sms_template.
        if channel == "sms":
            out[channel] = {
                "header_template": "",
                "body_template": str(data.get("sms_template") or ""),
                "footer_template": "",
            }
            continue

        out[channel] = {
            "header_template": str(data.get("header_template") or ""),
            "body_template": str(data.get("body_template") or ""),
            "footer_template": str(data.get("footer_template") or ""),
        }
    return out


def _validate_channel_templates(channels: list[str], channel_templates: dict[str, dict[str, str]]) -> None:
    for channel in channels:
        t = channel_templates.get(channel) or {}
        missing = [k for k in SUBTEMPLATE_KEYS if not str(t.get(k) or "").strip()]
        if missing:
            raise ValueError(
                f"channel_templates.{channel} must contain 3 non-empty subtemplates",
            )


def serialize_template(doc: dict) -> dict:
    out = dict(doc)
    out["_id"] = str(out["_id"])
    out["channels"] = _sanitize_channels(list(out.get("channels") or []))
    out["channel_templates"] = _build_channel_templates(out, out["channels"])

    # Compat legado para clientes ainda não migrados.
    email_like = (
        out["channel_templates"].get("email")
        or out["channel_templates"].get("whatsapp")
        or out["channel_templates"].get("pwa")
        or {"header_template": "", "body_template": "", "footer_template": ""}
    )
    sms_tpl = out["channel_templates"].get("sms") or {}
    out["header_template"] = str(email_like.get("header_template") or "")
    out["body_template"] = str(email_like.get("body_template") or "")
    out["footer_template"] = str(email_like.get("footer_template") or "")
    out["sms_template"] = str(sms_tpl.get("body_template") or "")
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

    channels = _sanitize_channels(data.get("channels") or [])
    if not isinstance(channels, list) or not channels:
        raise ValueError("At least one channel is required")

    channel_templates = _build_channel_templates(data, channels)
    _validate_channel_templates(channels, channel_templates)

    doc = {
        "name": name,
        "channels": channels,
        "channel_templates": channel_templates,
        "header_template": str(data.get("header_template") or ""),
        "body_template": str(data.get("body_template") or ""),
        "footer_template": str(data.get("footer_template") or ""),
        "sms_template": str(data.get("sms_template") or ""),
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
    current = db[COLLECTION].find_one({"_id": oid})
    if not current:
        raise ValueError("Template not found")

    for f in ["_id", "created_at"]:
        data.pop(f, None)

    if "name" in data and data["name"] is not None:
        data["name"] = str(data["name"]).strip()
        if not data["name"]:
            raise ValueError("Name cannot be empty")

    for key in (
        "header_template",
        "body_template",
        "footer_template",
        "sms_template",
    ):
        if key in data and data[key] is not None:
            data[key] = str(data[key])

    if "channels" in data:
        ch = _sanitize_channels(data["channels"])
        if not isinstance(ch, list) or not ch:
            raise ValueError("channels cannot be empty")
        data["channels"] = ch

    merged = dict(current)
    merged.update(data)
    merged_channels = _sanitize_channels(merged.get("channels") or [])
    merged_templates = _build_channel_templates(merged, merged_channels)
    _validate_channel_templates(merged_channels, merged_templates)
    data["channel_templates"] = merged_templates

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
    channels: list[str] | None = None,
    channel_templates: dict | None = None,
    header_template: str = "",
    body_template: str = "",
    footer_template: str = "",
    sms_template: str = "",
    *,
    preview_title: str = "Pré-visualização",
    brand_primary: str | None = None,
    brand_primary_foreground: str | None = None,
    logo_url: str | None = None,
) -> dict:
    channels_list = _sanitize_channels(channels or ["email", "whatsapp", "pwa", "sms"])
    raw = channel_templates if isinstance(channel_templates, dict) else {}
    if not raw:
        raw = {
            "email": {
                "header_template": header_template,
                "body_template": body_template,
                "footer_template": footer_template,
            },
            "whatsapp": {
                "header_template": header_template,
                "body_template": body_template,
                "footer_template": footer_template,
            },
            "pwa": {
                "header_template": header_template,
                "body_template": body_template,
                "footer_template": footer_template,
            },
            "sms": {
                "header_template": "",
                "body_template": sms_template,
                "footer_template": "",
            },
        }
    return render_preview_bundle(
        channels=channels_list,
        channel_templates=raw,
        preview_title=preview_title or "Pré-visualização",
        brand_primary=brand_primary,
        brand_primary_foreground=brand_primary_foreground,
        logo_url=logo_url,
    )


def test_pwa_payload(tenant_database: str, template_id: str) -> dict:
    doc = get_notification_template_by_id(tenant_database, template_id)
    if "pwa" not in [c.lower() for c in (doc.get("channels") or [])]:
        raise ValueError("Template does not include the pwa channel")
    bundle = render_preview_bundle(
        channels=doc.get("channels") or [],
        channel_templates=doc.get("channel_templates") or {},
        preview_title=doc.get("name") or "Notificação",
        brand_primary=None,
    )
    pwa = bundle.get("pwa") or {}
    return {
        "template_id": str(doc["_id"]),
        "title": str(pwa.get("title") or doc.get("name") or "Notificação"),
        "body": str(pwa.get("body") or ""),
    }
