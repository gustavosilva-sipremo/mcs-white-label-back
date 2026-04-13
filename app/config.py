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
