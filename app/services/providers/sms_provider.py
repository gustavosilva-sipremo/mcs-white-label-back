import json
import base64
from urllib import request

from app.config import (
    DISPATCH_PROVIDER_TIMEOUT_SECONDS,
    DISPATCH_SMS_API_KEY,
    DISPATCH_SMS_LOGIN,
    DISPATCH_SMS_PASSWORD,
    DISPATCH_SMS_PROVIDER_URL,
)


def send_sms(phone: str, message: str) -> dict:
    if (
        not DISPATCH_SMS_PROVIDER_URL
        or (not DISPATCH_SMS_API_KEY and not (DISPATCH_SMS_LOGIN and DISPATCH_SMS_PASSWORD))
    ):
        return {
            "status": "failed",
            "provider_message_id": None,
            "error": "SMS provider is not configured",
        }

    payload = json.dumps(
        {
            "messages": [
                {
                    "source": "python",
                    "body": message,
                    "to": phone,
                },
            ],
        },
    ).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if DISPATCH_SMS_API_KEY:
        headers["Authorization"] = f"Bearer {DISPATCH_SMS_API_KEY}"
    elif DISPATCH_SMS_LOGIN and DISPATCH_SMS_PASSWORD:
        token = base64.b64encode(
            f"{DISPATCH_SMS_LOGIN}:{DISPATCH_SMS_PASSWORD}".encode("utf-8"),
        ).decode("ascii")
        headers["Authorization"] = f"Basic {token}"

    req = request.Request(
        DISPATCH_SMS_PROVIDER_URL,
        data=payload,
        headers=headers,
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=DISPATCH_PROVIDER_TIMEOUT_SECONDS) as response:
            body = response.read().decode("utf-8")
        decoded = json.loads(body) if body else {}
        data = decoded.get("data") if isinstance(decoded, dict) else None
        first = data.get("messages")[0] if isinstance(data, dict) and data.get("messages") else {}
        return {
            "status": "sent",
            "provider_message_id": str(
                first.get("message_id")
                or first.get("messageId")
                or decoded.get("id")
                or decoded.get("message_id")
                or "",
            ),
            "error": None,
        }
    except Exception as exc:
        return {
            "status": "failed",
            "provider_message_id": None,
            "error": str(exc),
        }
