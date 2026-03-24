from fastapi import APIRouter, HTTPException

from app.models.user import UserCreate, UserUpdate
from app.services.user_service import (
    list_users,
    create_user,
    get_user_by_id,
    update_user,
    delete_user,
)

router = APIRouter(prefix="/{tenant_database}/users", tags=["Tenant Users"])


@router.get("")
async def get_users_by_tenant(tenant_database: str):
    try:
        users = list_users(tenant_database)
        return {"tenant": tenant_database, "users": users}

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("")
async def create_user_route(tenant_database: str, user: UserCreate):

    try:
        new_user = create_user(tenant_database, user.dict())
        return {"message": "User created successfully", "user": new_user}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{user_id}")
async def get_user_route(tenant_database: str, user_id: str):

    try:
        return get_user_by_id(tenant_database, user_id)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/{user_id}")
async def patch_user_route(tenant_database: str, user_id: str, user: UserUpdate):

    try:
        return update_user(tenant_database, user_id, user.dict(exclude_unset=True))

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{user_id}")
async def delete_user_route(tenant_database: str, user_id: str):

    try:
        return delete_user(tenant_database, user_id)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
