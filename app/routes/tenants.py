from fastapi import APIRouter, HTTPException
from app.services.user_service import list_users
from app.database.client import identity_db

from app.models.user import UserCreate, UserUpdate
from app.services.user_service import create_user
from app.services.user_service import (
    get_user_by_id,
    update_user,
    delete_user,
)

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


@router.post("/{tenant_database}/users")
async def create_user_route(tenant_database: str, user: UserCreate):

    try:
        new_user = create_user(tenant_database, user.dict())
        return {"message": "User created successfully", "user": new_user}

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{tenant_database}/users/{user_id}")
async def get_user_route(tenant_database: str, user_id: str):

    try:
        user = get_user_by_id(tenant_database, user_id)
        return user

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{tenant_database}/users/{user_id}")
async def update_user_route(tenant_database: str, user_id: str, user: UserUpdate):

    try:
        updated_user = update_user(
            tenant_database, user_id, user.dict(exclude_unset=True)
        )

        return updated_user

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{tenant_database}/users/{user_id}")
async def delete_user_route(tenant_database: str, user_id: str):

    try:
        return delete_user(tenant_database, user_id)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/{tenant_database}/users/{user_id}")
async def patch_user_route(tenant_database: str, user_id: str, user: UserUpdate):
    try:
        updated_user = update_user(
            tenant_database, user_id, user.dict(exclude_unset=True)
        )

        return updated_user

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
