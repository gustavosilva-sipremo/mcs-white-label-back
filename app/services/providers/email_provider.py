import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from app.config import (
    DISPATCH_EMAIL_SMTP_FROM,
    DISPATCH_EMAIL_SMTP_HOST,
    DISPATCH_EMAIL_SMTP_PASSWORD,
    DISPATCH_EMAIL_SMTP_PORT,
    DISPATCH_EMAIL_SMTP_USE_SSL,
    DISPATCH_EMAIL_SMTP_USE_TLS,
    DISPATCH_EMAIL_SMTP_USER,
)


def send_email(to_email: str, subject: str, html: str, text: str = "") -> dict:
    if not DISPATCH_EMAIL_SMTP_HOST or not DISPATCH_EMAIL_SMTP_FROM:
        return {
            "status": "failed",
            "provider_message_id": None,
            "error": "Email provider is not configured",
        }

    msg = MIMEMultipart("alternative")
    msg["From"] = DISPATCH_EMAIL_SMTP_FROM
    msg["To"] = to_email
    msg["Subject"] = subject
    if text.strip():
        msg.attach(MIMEText(text, "plain", "utf-8"))
    msg.attach(MIMEText(html or text or "", "html", "utf-8"))

    try:
        if DISPATCH_EMAIL_SMTP_USE_SSL:
            server = smtplib.SMTP_SSL(DISPATCH_EMAIL_SMTP_HOST, DISPATCH_EMAIL_SMTP_PORT)
        else:
            server = smtplib.SMTP(DISPATCH_EMAIL_SMTP_HOST, DISPATCH_EMAIL_SMTP_PORT)
        with server:
            if DISPATCH_EMAIL_SMTP_USE_TLS and not DISPATCH_EMAIL_SMTP_USE_SSL:
                server.starttls()
            if DISPATCH_EMAIL_SMTP_USER and DISPATCH_EMAIL_SMTP_PASSWORD:
                server.login(DISPATCH_EMAIL_SMTP_USER, DISPATCH_EMAIL_SMTP_PASSWORD)
            server.sendmail(DISPATCH_EMAIL_SMTP_FROM, [to_email], msg.as_string())
        return {"status": "sent", "provider_message_id": None, "error": None}
    except Exception as exc:
        return {
            "status": "failed",
            "provider_message_id": None,
            "error": str(exc),
        }
