import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
# Evolution API spam protection: space WhatsApp outbound to distinct numbers (seconds).
WHATSAPP_INTER_CONTACT_DELAY_SEC = 5.0


def _whatsapp_throttle_key(target: dict) -> str:
    """Stable key per destination contact for pacing WhatsApp sends."""
    wp = _normalize_phone(target.get("whatsapp"))
    if wp:
        return f"w:{wp}"
    ph = _normalize_phone(target.get("phone"))
    if ph:
        return f"w:{ph}"
    return f"t:{target.get('target_id', '')}"
ANSI_RESET = "\033[0m"
ANSI_BLUE = "\033[94m"
ANSI_GREEN = "\033[92m"
ANSI_YELLOW = "\033[93m"
ANSI_RED = "\033[91m"


def _log_dispatch(message: str, level: str = "info") -> None:
    color = ANSI_BLUE
    if level == "success":
        color = ANSI_GREEN
    elif level == "warn":
        color = ANSI_YELLOW
    elif level == "error":
        color = ANSI_RED
    print(f"{color}[dispatch]{ANSI_RESET} {message}")


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
        if key == ("", "", ""):
            continue
        if key in seen:
            continue
        seen.add(key)
        deduped.append(target)
    return deduped


def normalize_resolved_manual_targets(raw: list[dict] | None) -> list[dict]:
    """Build dispatch targets from loosely typed dicts ({name, email, phone, whatsapp?, target_id?, source})."""
    targets: list[dict] = []
    for idx, t in enumerate(raw or []):
        if not isinstance(t, dict):
            continue
        tid = str(t.get("target_id") or "").strip()
        targets.append(
            {
                "target_id": tid or f"target-{idx + 1}",
                "name": str(t.get("name") or f"Destinatário {idx + 1}"),
                "email": _normalize_email(t.get("email")),
                "phone": _normalize_phone(t.get("phone")),
                "whatsapp": _normalize_phone(t.get("whatsapp") or t.get("phone")),
                "source": str(t.get("source") or "resolved"),
            },
        )
    deduped: list[dict] = []
    seen_uid: set[str] = set()
    seen_tpl: set[tuple[str, str, str]] = set()
    for target in targets:
        tid = str(target["target_id"] or "").strip()
        if tid and tid.startswith("user-"):
            if tid in seen_uid:
                continue
            seen_uid.add(tid)
            deduped.append(target)
            continue
        key = (target["email"], target["phone"], target["whatsapp"])
        if key == ("", "", ""):
            continue
        if key in seen_tpl:
            continue
        seen_tpl.add(key)
        deduped.append(target)
    return deduped


def render_dispatch_for_targets(
    tenant_database: str,
    template: dict,
    effective_channels: list[str],
    targets: list[dict],
    *,
    preview_title: str | None,
    channel_templates_override: dict | None = None,
    brand_primary: str | None = None,
    brand_primary_foreground: str | None = None,
    logo_url: str | None = None,
) -> tuple[dict[str, int], list[dict]]:
    """Render templates once and run _dispatch_channel for each target/channel. Targets must match _build_targets shape."""
    template_id_str = str(template.get("_id") or "") if template else ""
    merged_channel_templates = channel_templates_override or template.get("channel_templates") or {}
    rendered = preview_notification_templates(
        channels=effective_channels,
        channel_templates=merged_channel_templates,
        preview_title=preview_title or template.get("name") or "Notificação",
        brand_primary=brand_primary,
        brand_primary_foreground=brand_primary_foreground,
        logo_url=logo_url,
    )
    delivery_logs: list[dict] = []
    summary: dict[str, int] = {"sent": 0, "failed": 0, "ignored": 0}
    title_final = preview_title or template.get("name") or "Notificação"
    non_whatsapp_jobs: list[tuple[int, int, dict, str]] = []
    whatsapp_jobs: list[tuple[int, int, dict, str]] = []
    for ti, target in enumerate(targets):
        for ci, channel in enumerate(effective_channels):
            job = (ti, ci, target, channel)
            if channel == "whatsapp":
                whatsapp_jobs.append(job)
            else:
                non_whatsapp_jobs.append(job)

    def _dispatch_one(target: dict, channel: str) -> dict:
        try:
            return _dispatch_channel(
                channel=channel,
                target=target,
                rendered=rendered,
                title=str(title_final),
            )
        except Exception as exc:
            return {
                "status": "failed",
                "error": str(exc),
                "provider_message_id": None,
            }

    ordered_results: list[tuple[int, int, dict, str, dict]] = []

    if non_whatsapp_jobs:
        max_workers = max(1, min(16, len(non_whatsapp_jobs)))
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {
                executor.submit(_dispatch_one, target, channel): (
                    ti,
                    ci,
                    target,
                    channel,
                )
                for ti, ci, target, channel in non_whatsapp_jobs
            }
            for future in as_completed(future_map):
                ti, ci, target, channel = future_map[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = {
                        "status": "failed",
                        "error": str(exc),
                        "provider_message_id": None,
                    }
                ordered_results.append((ti, ci, target, channel, result))

    prev_wa_contact_key: str | None = None
    for ti, ci, target, channel in whatsapp_jobs:
        contact_key = _whatsapp_throttle_key(target)
        if (
            prev_wa_contact_key is not None
            and contact_key != prev_wa_contact_key
        ):
            time.sleep(WHATSAPP_INTER_CONTACT_DELAY_SEC)
        ordered_results.append(
            (ti, ci, target, channel, _dispatch_one(target, channel)),
        )
        prev_wa_contact_key = contact_key

    ordered_results.sort(key=lambda x: (x[0], x[1]))
    for _, _, target, channel, channel_result in ordered_results:
        status = str(channel_result.get("status") or "failed")
        summary[status] = summary.get(status, 0) + 1
        if status == "sent":
            _log_dispatch(
                f"{channel} -> {target['name']} status=sent provider_id={channel_result.get('provider_message_id') or '-'}",
                "success",
            )
        elif status == "ignored":
            _log_dispatch(
                f"{channel} -> {target['name']} status=ignored reason={channel_result.get('error')}",
                "warn",
            )
        else:
            _log_dispatch(
                f"{channel} -> {target['name']} status=failed error={channel_result.get('error')}",
                "error",
            )
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
    return summary, delivery_logs


def dispatch_template_for_manual_targets_only(
    tenant_database: str,
    template_id: str,
    requested_channels: list[str],
    manual_targets_normalized: list[dict],
    *,
    preview_title: str | None = None,
    channel_templates_override: dict | None = None,
    brand_primary: str | None = None,
    brand_primary_foreground: str | None = None,
    logo_url: str | None = None,
    insert_dispatch_test_log: bool = False,
    acting_user_snapshot: dict | None = None,
) -> dict[str, Any]:
    """
    Dispatch template to arbitrary resolved targets (no logged-in recipient).
    Optionally persists to notification_test_dispatch_logs (test UI).
    Used by flow instance notification steps.
    """
    _log_dispatch(f"manual-only tenant={tenant_database} template={template_id} targets={len(manual_targets_normalized)}")
    template = get_notification_template_by_id(tenant_database, template_id)
    enabled_template_channels = [
        str(c).strip().lower()
        for c in (template.get("channels") or [])
        if str(c).strip().lower() in SUPPORTED_CHANNELS
    ]
    requested = [
        str(c).strip().lower() for c in (requested_channels or []) if str(c).strip().lower() in SUPPORTED_CHANNELS
    ]
    effective_channels = [c for c in requested if c in enabled_template_channels]
    if not effective_channels:
        raise ValueError("No valid channels selected for this template")
    targets = normalize_resolved_manual_targets(manual_targets_normalized)
    if not targets:
        raise ValueError("No recipients resolved for notification step")
    tid_key = str(template_id).strip()
    summary, deliveries = render_dispatch_for_targets(
        tenant_database,
        template,
        effective_channels,
        targets,
        preview_title=preview_title,
        channel_templates_override=channel_templates_override,
        brand_primary=brand_primary,
        brand_primary_foreground=brand_primary_foreground,
        logo_url=logo_url,
    )
    dispatch_id: str | None = None
    if insert_dispatch_test_log:
        db = get_tenant_db(tenant_database)
        au = acting_user_snapshot or {}
        payload = {
            "template_id": tid_key,
            "template_name": template.get("name"),
            "channels": effective_channels,
            "tenant_database": tenant_database,
            "triggered_by_user_id": str(au.get("user_id") or au.get("_id") or ""),
            "triggered_by_name": str(au.get("name") or ""),
            "preview_title": preview_title,
            "summary": summary,
            "deliveries": deliveries,
            "created_at": now_brasilia(),
        }
        insert_result = db[DISPATCH_LOG_COLLECTION].insert_one(payload)
        dispatch_id = str(insert_result.inserted_id)
    _log_dispatch(
        f"finished manual-only dispatch_id={dispatch_id} summary={summary}",
        "success" if summary.get("failed", 0) == 0 else "warn",
    )
    return {
        "dispatch_id": dispatch_id,
        "template_id": tid_key,
        "channels": effective_channels,
        "summary": summary,
        "deliveries": deliveries,
    }


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
    _log_dispatch(
        f"start tenant={tenant_database} template={template_id} channels={channels}",
    )
    template = get_notification_template_by_id(tenant_database, template_id)
    enabled_template_channels = [
        str(c).strip().lower() for c in (template.get("channels") or []) if str(c).strip().lower() in SUPPORTED_CHANNELS
    ]
    requested_channels = [
        str(c).strip().lower() for c in (channels or []) if str(c).strip().lower() in SUPPORTED_CHANNELS
    ]
    effective_channels = [c for c in requested_channels if c in enabled_template_channels]
    if not effective_channels:
        _log_dispatch("no effective channels for this template", "warn")
        raise ValueError("No valid channels selected for this template")

    targets = _build_targets(current_user, use_logged_user, manual_targets or [])
    if not targets:
        _log_dispatch("no valid targets provided", "warn")
        raise ValueError("No valid targets provided")

    _log_dispatch(
        f"targets={len(targets)} effective_channels={effective_channels}",
    )

    merged_channel_templates = channel_templates or template.get("channel_templates") or {}
    if logo_url:
        logo_kind = "data-uri" if str(logo_url).startswith("data:image/") else "url"
        _log_dispatch(f"email logo provided ({logo_kind})")
    title_use = preview_title or template.get("name") or "Teste de notificação"

    summary, delivery_logs = render_dispatch_for_targets(
        tenant_database,
        template,
        effective_channels,
        targets,
        preview_title=title_use,
        channel_templates_override=merged_channel_templates,
        brand_primary=brand_primary,
        brand_primary_foreground=brand_primary_foreground,
        logo_url=logo_url,
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
    _log_dispatch(
        f"finished dispatch_id={insert_result.inserted_id} summary={summary}",
        "success" if summary.get("failed", 0) == 0 else "warn",
    )

    return {
        "dispatch_id": str(insert_result.inserted_id),
        "template_id": template_id,
        "channels": effective_channels,
        "summary": summary,
        "deliveries": delivery_logs,
    }
