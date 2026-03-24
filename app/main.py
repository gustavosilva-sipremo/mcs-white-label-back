from fastapi import FastAPI

from app.routes import tenants
from app.routes import tenant_users
from app.routes import auth


# =========================
# App
# =========================
app = FastAPI(
    title="MCS White Label Backend",
    description="Multi-tenant backend for the MCS White Label platform",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)


# =========================
# Routers
# =========================
app.include_router(
    tenants.router,
    prefix="/tenants",
)

app.include_router(
    tenant_users.router,
    prefix="/tenants",
)

app.include_router(
    auth.router,
)


# =========================
# Health Check
# =========================
@app.get(
    "/health",
    tags=["System"],
    summary="Health check",
)
def health_check():
    """
    Endpoint usado para verificar se a API está funcionando.
    Utilizado por monitoramento, docker healthcheck, etc.
    """
    return {"status": "ok"}


# =========================
# Root
# =========================
@app.get(
    "/",
    tags=["System"],
    summary="API root",
)
def root():
    """
    Endpoint raiz da API.
    """
    return {
        "message": "MCS White Label Backend is running",
        "version": "1.0.0",
    }
