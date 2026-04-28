import json
from urllib import request, parse, error

from app.config import (
    DISPATCH_PROVIDER_TIMEOUT_SECONDS,
    DISPATCH_WHATSAPP_API_KEY,
    DISPATCH_WHATSAPP_INSTANCE_NAME,
    DISPATCH_WHATSAPP_PROVIDER_URL,
)


def send_whatsapp(phone: str, message: str) -> dict:
    if (
        not DISPATCH_WHATSAPP_PROVIDER_URL
        or not DISPATCH_WHATSAPP_API_KEY
        or not DISPATCH_WHATSAPP_INSTANCE_NAME
    ):
        return {
            "status": "failed",
            "provider_message_id": None,
            "error": "WhatsApp provider is not configured",
        }

    payload = json.dumps({"number": phone, "text": message}).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "apikey": DISPATCH_WHATSAPP_API_KEY,
    }

    base = DISPATCH_WHATSAPP_PROVIDER_URL.rstrip("/")
    raw_instance = DISPATCH_WHATSAPP_INSTANCE_NAME.strip()
    decoded_instance = parse.unquote(raw_instance)
    candidates = [
        f"{base}/message/sendText/{raw_instance}",
        f"{base}/message/sendText/{parse.quote(decoded_instance, safe='')}",
    ]

    last_error = "Unknown whatsapp error"
    for endpoint in candidates:
        req = request.Request(
            endpoint,
            data=payload,
            headers=headers,
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=DISPATCH_PROVIDER_TIMEOUT_SECONDS) as response:
                body = response.read().decode("utf-8")
            decoded = json.loads(body) if body else {}
            return {
                "status": "sent",
                "provider_message_id": str(
                    decoded.get("id") or decoded.get("message_id") or "",
                ),
                "error": None,
            }
        except error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="ignore")
            last_error = f"HTTP {exc.code} on {endpoint}: {details or exc.reason}"
        except Exception as exc:
            last_error = str(exc)

    return {
        "status": "failed",
        "provider_message_id": None,
        "error": last_error,
    }
