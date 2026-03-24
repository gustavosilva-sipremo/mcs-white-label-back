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

# =========================
# Tokens
# =========================
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", 15))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", 30))

ACCESS_TOKEN_EXPIRE = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
REFRESH_TOKEN_EXPIRE = timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS)
