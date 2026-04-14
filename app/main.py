# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import tenants, tenant_users, tenant_teams, tenant_lists, auth

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
# CORS
# =========================
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite dev server padrão
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =========================
# Routers
# =========================
app.include_router(
    tenants.router,
    prefix="/tenants",
    tags=["Tenants"],
)

app.include_router(
    tenant_users.router,
    prefix="/tenants",
    tags=["Tenant Users"],
)

app.include_router(
    tenant_teams.router,
    prefix="/tenants",
    tags=["Tenant Teams"],
)

app.include_router(
    tenant_lists.router,
    prefix="/tenants",
    tags=["Tenant Lists"],
)

app.include_router(
    auth.router,
    tags=["Auth"],
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
