from fastapi import APIRouter, HTTPException
from app.services.user_service import list_users
from app.database.client import identity_db

router = APIRouter()


# Listar todos os tenants
@router.get("/all")
async def get_all_tenants():
    tenants = list(identity_db.tenants.find({}))
    for tenant in tenants:
        tenant["_id"] = str(tenant["_id"])
    return {"tenants": tenants}


# Listar todos os usuários de um tenant
@router.get("/{tenant_database}/users")
async def get_users_by_tenant(tenant_database: str):
    try:
        users = list_users(tenant_database)
        return {"tenant": tenant_database, "users": users}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
