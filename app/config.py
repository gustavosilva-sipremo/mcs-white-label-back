import os
from dotenv import load_dotenv
from datetime import timedelta

# Carrega variáveis do .env
load_dotenv()

# =========================
# MongoDB
# =========================
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")

# =========================
# JWT
# =========================
JWT_SECRET = os.getenv("JWT_SECRET", "super-secret-key")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
# Refresh JWTs are signed with this secret (defaults to a distinct value so a refresh token cannot be used as a Bearer access token when only JWT_SECRET is set).
REFRESH_JWT_SECRET = os.getenv("REFRESH_JWT_SECRET") or f"{JWT_SECRET}:refresh"

# =========================
# Tokens
# =========================
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 30))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 15))

ACCESS_TOKEN_EXPIRE = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
REFRESH_TOKEN_EXPIRE = timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)

# =========================
# Dispatch providers
# =========================
DISPATCH_EMAIL_SMTP_HOST = os.getenv("DISPATCH_EMAIL_SMTP_HOST") or os.getenv(
    "EMAIL_SMTP",
    "",
)
DISPATCH_EMAIL_SMTP_PORT = int(
    os.getenv("DISPATCH_EMAIL_SMTP_PORT") or os.getenv("EMAIL_PORT", "587"),
)
DISPATCH_EMAIL_SMTP_USER = os.getenv("DISPATCH_EMAIL_SMTP_USER") or os.getenv(
    "EMAIL_USER",
    "",
)
DISPATCH_EMAIL_SMTP_PASSWORD = os.getenv("DISPATCH_EMAIL_SMTP_PASSWORD") or os.getenv(
    "EMAIL_PASSWORD",
    "",
)
DISPATCH_EMAIL_SMTP_FROM = os.getenv("DISPATCH_EMAIL_SMTP_FROM") or os.getenv(
    "EMAIL_SENDER",
    "",
)
DISPATCH_EMAIL_SMTP_USE_TLS = os.getenv("DISPATCH_EMAIL_SMTP_USE_TLS", "true").lower() == "true"
DISPATCH_EMAIL_SMTP_USE_SSL = (
    os.getenv("DISPATCH_EMAIL_SMTP_USE_SSL", "false").lower() == "true"
    or str(DISPATCH_EMAIL_SMTP_PORT) == "465"
)
DISPATCH_PROVIDER_TIMEOUT_SECONDS = float(
    os.getenv("DISPATCH_PROVIDER_TIMEOUT_SECONDS", "10"),
)

DISPATCH_SMS_PROVIDER_URL = os.getenv("DISPATCH_SMS_PROVIDER_URL") or os.getenv(
    "CLICKSEND_URL",
    "https://rest.clicksend.com/v3/sms/send",
)
DISPATCH_SMS_API_KEY = os.getenv("DISPATCH_SMS_API_KEY", "")
DISPATCH_SMS_LOGIN = os.getenv("DISPATCH_SMS_LOGIN") or os.getenv("LOGIN_API_CLICKSEND", "")
DISPATCH_SMS_PASSWORD = os.getenv("DISPATCH_SMS_PASSWORD") or os.getenv(
    "PASSWORD_API_CLICKSEND",
    "",
)

DISPATCH_WHATSAPP_PROVIDER_URL = os.getenv("DISPATCH_WHATSAPP_PROVIDER_URL") or os.getenv(
    "EVOLUTION_URL",
    "",
)
DISPATCH_WHATSAPP_API_KEY = os.getenv("DISPATCH_WHATSAPP_API_KEY") or os.getenv(
    "EVOLUTION_API_KEY",
    "",
)
DISPATCH_WHATSAPP_INSTANCE_NAME = os.getenv("DISPATCH_WHATSAPP_INSTANCE_NAME") or os.getenv(
    "EVOLUTION_INSTANCE_NAME",
    "",
)
