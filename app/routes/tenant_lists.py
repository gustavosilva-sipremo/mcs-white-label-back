from fastapi import APIRouter, HTTPException, Depends

from app.dependencies.auth_dependency import require_admin_same_tenant
from app.models.tenant_list import GenericListCreate, GenericListUpdate
from app.services.tenant_list_service import (
    list_generic_lists,
    create_generic_list,
    get_generic_list_by_id,
    update_generic_list,
    delete_generic_list,
)

router = APIRouter(prefix="/{tenant_database}/lists", tags=["Tenant Lists"])


@router.get("")
async def list_generic_lists_route(
    tenant_database: str,
    _admin=Depends(require_admin_same_tenant),
):
    try:
        lists = list_generic_lists(tenant_database)
        return {"tenant": tenant_database, "lists": lists}
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def create_generic_list_route(
    tenant_database: str,
    body: GenericListCreate,
    _admin=Depends(require_admin_same_tenant),
):
    try:
        doc = create_generic_list(tenant_database, body.model_dump(exclude_none=True))
        return {"message": "List created successfully", "list": doc}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{list_id}")
async def get_generic_list_route(
    tenant_database: str,
    list_id: str,
    _admin=Depends(require_admin_same_tenant),
):
    try:
        return get_generic_list_by_id(tenant_database, list_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/{list_id}")
async def patch_generic_list_route(
    tenant_database: str,
    list_id: str,
    body: GenericListUpdate,
    _admin=Depends(require_admin_same_tenant),
):
    try:
        return update_generic_list(
            tenant_database, list_id, body.model_dump(exclude_unset=True)
        )
    except ValueError as e:
        msg = str(e)
        code = 404 if "not found" in msg.lower() else 400
        raise HTTPException(status_code=code, detail=msg)


@router.delete("/{list_id}")
async def delete_generic_list_route(
    tenant_database: str,
    list_id: str,
    _admin=Depends(require_admin_same_tenant),
):
    try:
        return delete_generic_list(tenant_database, list_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
