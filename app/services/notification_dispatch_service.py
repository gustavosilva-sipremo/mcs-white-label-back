import re
from typing import Any

from app.database.client import get_tenant_db
from app.services.notification_template_service import (
    get_notification_template_by_id,
    preview_notification_templates,
)
from app.services.providers.email_provider import send_email
from app.services.providers.sms_provider import send_sms
from app.services.providers.whatsapp_provider import send_whatsapp
from app.utils.datetime_utils import now_brasilia

DISPATCH_LOG_COLLECTION = "notification_test_dispatch_logs"
SUPPORTED_CHANNELS = ("email", "sms", "whatsapp", "pwa")


def _normalize_email(value: str | None) -> str:
    return str(value or "").strip().lower()


def _normalize_phone(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    if raw.startswith("+"):
        return "+" + re.sub(r"\D", "", raw[1:])
    return "+" + re.sub(r"\D", "", raw)


def _build_targets(current_user: dict, use_logged_user: bool, manual_targets: list[dict]) -> list[dict]:
    targets: list[dict] = []
    if use_logged_user:
        targets.append(
            {
                "target_id": str(current_user.get("_id") or "logged-user"),
                "name": str(current_user.get("name") or "Usuário logado"),
                "email": _normalize_email(current_user.get("email")),
                "phone": _normalize_phone(current_user.get("phone")),
                "whatsapp": _normalize_phone(current_user.get("phone")),
                "source": "logged_user",
            },
        )
    for idx, target in enumerate(manual_targets or []):
        if not isinstance(target, dict):
            continue
        targets.append(
            {
                "target_id": f"manual-{idx + 1}",
                "name": str(target.get("name") or f"Contato manual {idx + 1}"),
                "email": _normalize_email(target.get("email")),
                "phone": _normalize_phone(target.get("phone")),
                "whatsapp": _normalize_phone(target.get("whatsapp") or target.get("phone")),
                "source": "manual",
            },
        )
    deduped: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for target in targets:
        key = (target["email"], target["phone"], target["whatsapp"])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(target)
    return deduped


def _dispatch_channel(channel: str, target: dict, rendered: dict, title: str) -> dict:
    if channel == "email":
        if not target.get("email"):
            return {"status": "ignored", "error": "missing email", "provider_message_id": None}
        result = send_email(
            to_email=target["email"],
            subject=title,
            html=str(rendered.get("email_html") or ""),
            text=str(rendered.get("main_plain") or ""),
        )
        return result

    if channel == "sms":
        if not target.get("phone"):
            return {"status": "ignored", "error": "missing phone", "provider_message_id": None}
        result = send_sms(
            phone=target["phone"],
            message=str(rendered.get("sms_text") or ""),
        )
        return result

    if channel == "whatsapp":
        if not target.get("whatsapp"):
            return {"status": "ignored", "error": "missing whatsapp", "provider_message_id": None}
        result = send_whatsapp(
            phone=target["whatsapp"],
            message=str(rendered.get("whatsapp_text") or ""),
        )
        return result

    if channel == "pwa":
        # PWA teste é local: reporta envio virtual.
        return {"status": "sent", "error": None, "provider_message_id": "pwa-local"}

    return {"status": "ignored", "error": f"unsupported channel: {channel}", "provider_message_id": None}


def dispatch_template_test(
    tenant_database: str,
    template_id: str,
    channels: list[str],
    current_user: dict,
    *,
    use_logged_user: bool = True,
    manual_targets: list[dict] | None = None,
    preview_title: str = "Teste de notificação",
    channel_templates: dict | None = None,
    brand_primary: str | None = None,
    brand_primary_foreground: str | None = None,
    logo_url: str | None = None,
) -> dict[str, Any]:
    template = get_notification_template_by_id(tenant_database, template_id)
    enabled_template_channels = [
        str(c).strip().lower() for c in (template.get("channels") or []) if str(c).strip().lower() in SUPPORTED_CHANNELS
    ]
    requested_channels = [
        str(c).strip().lower() for c in (channels or []) if str(c).strip().lower() in SUPPORTED_CHANNELS
    ]
    effective_channels = [c for c in requested_channels if c in enabled_template_channels]
    if not effective_channels:
        raise ValueError("No valid channels selected for this template")

    targets = _build_targets(current_user, use_logged_user, manual_targets or [])
    if not targets:
        raise ValueError("No valid targets provided")

    merged_channel_templates = channel_templates or template.get("channel_templates") or {}
    rendered = preview_notification_templates(
        channels=effective_channels,
        channel_templates=merged_channel_templates,
        preview_title=preview_title or template.get("name") or "Teste de notificação",
        brand_primary=brand_primary,
        brand_primary_foreground=brand_primary_foreground,
        logo_url=logo_url,
    )

    delivery_logs: list[dict] = []
    summary = {"sent": 0, "failed": 0, "ignored": 0}
    for target in targets:
        for channel in effective_channels:
            channel_result = _dispatch_channel(
                channel=channel,
                target=target,
                rendered=rendered,
                title=preview_title or template.get("name") or "Teste de notificação",
            )
            status = str(channel_result.get("status") or "failed")
            summary[status] = summary.get(status, 0) + 1
            delivery_logs.append(
                {
                    "channel": channel,
                    "status": status,
                    "target_id": target["target_id"],
                    "target_name": target["name"],
                    "target_source": target["source"],
                    "email": target.get("email"),
                    "phone": target.get("phone"),
                    "whatsapp": target.get("whatsapp"),
                    "provider_message_id": channel_result.get("provider_message_id"),
                    "error": channel_result.get("error"),
                    "created_at": now_brasilia(),
                },
            )

    db = get_tenant_db(tenant_database)
    payload = {
        "template_id": template_id,
        "template_name": template.get("name"),
        "channels": effective_channels,
        "tenant_database": tenant_database,
        "triggered_by_user_id": str(current_user.get("_id") or ""),
        "triggered_by_name": str(current_user.get("name") or ""),
        "preview_title": preview_title,
        "summary": summary,
        "deliveries": delivery_logs,
        "created_at": now_brasilia(),
    }
    insert_result = db[DISPATCH_LOG_COLLECTION].insert_one(payload)

    return {
        "dispatch_id": str(insert_result.inserted_id),
        "template_id": template_id,
        "channels": effective_channels,
        "summary": summary,
        "deliveries": delivery_logs,
    }
