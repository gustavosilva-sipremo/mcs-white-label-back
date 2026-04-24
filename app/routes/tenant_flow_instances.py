from fastapi import APIRouter, Body, Depends, HTTPException

from app.dependencies.auth_dependency import require_user_same_tenant
from app.models.flow_instance import FlowInstanceAdvance, FlowInstanceCreate
from app.services import flow_instance_service

router = APIRouter(
    prefix="/{tenant_database}/flow-instances",
    tags=["Flow Instances"],
)


@router.post("")
async def create_flow_instance_route(
    tenant_database: str,
    body: FlowInstanceCreate,
    user=Depends(require_user_same_tenant),
):
    try:
        inst = flow_instance_service.create_flow_instance(
            tenant_database,
            entry_branch_key=body.entry_branch_key,
            created_by=str(user["_id"]),
            client_request_id=body.client_request_id,
        )
        return {"message": "Flow instance created", "instance": inst}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/{instance_id}")
async def get_flow_instance_route(
    tenant_database: str,
    instance_id: str,
    _user=Depends(require_user_same_tenant),
):
    try:
        return {"instance": flow_instance_service.get_flow_instance(tenant_database, instance_id)}
    except ValueError as e:
        msg = str(e)
        code = 404 if "not found" in msg.lower() else 400
        raise HTTPException(status_code=code, detail=msg) from e


@router.patch("/{instance_id}/advance")
async def advance_flow_instance_route(
    tenant_database: str,
    instance_id: str,
    body: FlowInstanceAdvance = Body(default_factory=FlowInstanceAdvance),
    _user=Depends(require_user_same_tenant),
):
    try:
        payload = body.payload
        inst = flow_instance_service.advance_flow_instance(
            tenant_database,
            instance_id,
            payload=payload,
        )
        return {"message": "Flow instance updated", "instance": inst}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
