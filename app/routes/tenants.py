from fastapi import APIRouter, HTTPException

from app.services.tenant_service import (
    list_tenants,
    create_tenant,
    get_tenant_by_id,
    update_tenant,
    delete_tenant,
)

router = APIRouter(prefix="/tenants", tags=["Tenants"])


# =========================
# List Tenants
# =========================
@router.get("")
async def get_all_tenants():
    try:
        tenants = list_tenants()
        return {"tenants": tenants}

    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


# =========================
# Create Tenant
# =========================
@router.post("")
async def create_tenant_route(tenant: dict):

    try:
        new_tenant = create_tenant(tenant)
        return {"message": "Tenant created successfully", "tenant": new_tenant}

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


# =========================
# Get Tenant
# =========================
@router.get("/{tenant_id}")
async def get_tenant_route(tenant_id: str):

    try:
        return get_tenant_by_id(tenant_id)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# =========================
# Update Tenant
# =========================
@router.patch("/{tenant_id}")
async def update_tenant_route(tenant_id: str, tenant: dict):

    try:
        return update_tenant(tenant_id, tenant)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


# =========================
# Delete Tenant
# =========================
@router.delete("/{tenant_id}")
async def delete_tenant_route(tenant_id: str):

    try:
        return delete_tenant(tenant_id)

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
