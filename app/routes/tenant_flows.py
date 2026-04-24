from fastapi import APIRouter, Depends, HTTPException

from app.dependencies.auth_dependency import (
    require_admin_same_tenant,
    require_user_same_tenant,
)
from app.models.flow import FlowCreate, FlowUpdate, FlowVersionSave
from app.services import flow_service

router = APIRouter(
    prefix="/{tenant_database}/flows",
    tags=["Tenant Flows"],
)


def _admin_id(admin: dict) -> str | None:
    uid = admin.get("_id")
    return str(uid) if uid else None


@router.get("")
async def list_flows_route(
    tenant_database: str,
    _admin=Depends(require_admin_same_tenant),
):
    try:
        items = flow_service.list_flows(tenant_database)
        return {"tenant": tenant_database, "flows": items}
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def create_flow_route(
    tenant_database: str,
    body: FlowCreate,
    admin=Depends(require_admin_same_tenant),
):
    try:
        payload = body.model_dump(exclude_none=True)
        doc = flow_service.create_flow(
            tenant_database,
            payload,
            created_by=_admin_id(admin),
        )
        return {"message": "Flow created successfully", "flow": doc}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/main/current-plan")
async def main_flow_current_plan_route(
    tenant_database: str,
    _user=Depends(require_user_same_tenant),
):
    try:
        return flow_service.get_main_flow_current_plan(tenant_database)
    except ValueError as e:
        msg = str(e)
        code = 404 if "not found" in msg.lower() else 400
        raise HTTPException(status_code=code, detail=msg) from e


@router.get("/{flow_id}")
async def get_flow_route(
    tenant_database: str,
    flow_id: str,
    _admin=Depends(require_admin_same_tenant),
):
    try:
        return flow_service.get_flow_with_current(tenant_database, flow_id)
    except ValueError as e:
        msg = str(e)
        code = 404 if "not found" in msg.lower() else 400
        raise HTTPException(status_code=code, detail=msg)


@router.patch("/{flow_id}")
async def patch_flow_route(
    tenant_database: str,
    flow_id: str,
    body: FlowUpdate,
    _admin=Depends(require_admin_same_tenant),
):
    try:
        return flow_service.update_flow(
            tenant_database,
            flow_id,
            body.model_dump(exclude_unset=True),
        )
    except ValueError as e:
        msg = str(e)
        code = 404 if "not found" in msg.lower() else 400
        raise HTTPException(status_code=code, detail=msg)


@router.get("/{flow_id}/versions")
async def list_versions_route(
    tenant_database: str,
    flow_id: str,
    _admin=Depends(require_admin_same_tenant),
):
    try:
        items = flow_service.list_flow_versions(tenant_database, flow_id)
        return {"tenant": tenant_database, "flow_id": flow_id, "versions": items}
    except ValueError as e:
        msg = str(e)
        code = 404 if "not found" in msg.lower() else 400
        raise HTTPException(status_code=code, detail=msg)


@router.get("/{flow_id}/versions/{version}")
async def get_version_route(
    tenant_database: str,
    flow_id: str,
    version: int,
    _admin=Depends(require_admin_same_tenant),
):
    try:
        return flow_service.get_flow_version(
            tenant_database,
            flow_id,
            version,
            include_graph=True,
        )
    except ValueError as e:
        msg = str(e)
        code = 404 if "not found" in msg.lower() else 400
        raise HTTPException(status_code=code, detail=msg)


@router.post("/{flow_id}/versions")
async def save_version_route(
    tenant_database: str,
    flow_id: str,
    body: FlowVersionSave,
    admin=Depends(require_admin_same_tenant),
):
    try:
        doc = flow_service.save_new_version(
            tenant_database,
            flow_id,
            body.graph.model_dump(),
            created_by=_admin_id(admin),
        )
        return {"message": "Flow version saved successfully", "flow": doc}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/{flow_id}/rollback/{version}")
async def rollback_route(
    tenant_database: str,
    flow_id: str,
    version: int,
    admin=Depends(require_admin_same_tenant),
):
    try:
        doc = flow_service.rollback_to_version(
            tenant_database,
            flow_id,
            version,
            created_by=_admin_id(admin),
        )
        return {"message": "Flow rolled back successfully", "flow": doc}
    except ValueError as e:
        msg = str(e)
        code = 404 if "not found" in msg.lower() else 400
        raise HTTPException(status_code=code, detail=msg)
