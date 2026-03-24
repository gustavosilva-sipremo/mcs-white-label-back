from fastapi import FastAPI

from app.routes import tenants
from app.routes import tenant_users

app = FastAPI(title="MCS White Label Backend")


# Rotas de tenants
app.include_router(
    tenants.router,
    prefix="/tenants",
    tags=["Tenants"],
)

# Rotas de usuários dentro de tenants
app.include_router(
    tenant_users.router,
    prefix="/tenants",
    tags=["Tenant Users"],
)


@app.get("/")
def root():
    return {"message": "MCS White Label Backend is running"}
