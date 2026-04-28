from fastapi import APIRouter, Body, Depends, HTTPException

from app.dependencies.auth_dependency import require_user_same_tenant
from app.models.flow_instance import FlowInstanceAdvance, FlowInstanceCreate
from app.services import flow_instance_service

router = APIRouter(
    prefix="/{tenant_database}/flow-instances",
    tags=["Flow Instances"],
)


@router.get("")
async def list_flow_instances_route(
    tenant_database: str,
    _user=Depends(require_user_same_tenant),
):
    try:
        items = flow_instance_service.list_active_flow_instances(tenant_database)
        return {"tenant": tenant_database, "instances": items}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e


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
            acting_user=user,
            client_request_id=body.client_request_id,
            trigger_answers=body.trigger_answers,
        )
        return {"message": "Flow instance created", "instance": inst}
    except ValueError as e:
        msg = str(e)
        low = msg.lower()
        if "not allowed" in low:
            raise HTTPException(status_code=403, detail=msg) from e
        raise HTTPException(status_code=400, detail=msg) from e


@router.patch("/{instance_id}/end")
async def end_flow_instance_route(
    tenant_database: str,
    instance_id: str,
    user=Depends(require_user_same_tenant),
):
    try:
        inst = flow_instance_service.end_flow_instance_by_user(
            tenant_database,
            instance_id,
            acting_user=user,
        )
        return {"message": "Flow instance ended", "instance": inst}
    except ValueError as e:
        msg = str(e)
        low = msg.lower()
        if "not found" in low:
            code = 404
        elif "not allowed" in low:
            code = 403
        else:
            code = 400
        raise HTTPException(status_code=code, detail=msg) from e


@router.get("/{instance_id}")
async def get_flow_instance_route(
    tenant_database: str,
    instance_id: str,
    user=Depends(require_user_same_tenant),
):
    try:
        return {
            "instance": flow_instance_service.get_flow_instance(
                tenant_database,
                instance_id,
                actor=user,
            ),
        }
    except ValueError as e:
        msg = str(e)
        low = msg.lower()
        if "not found" in low:
            code = 404
        elif "not allowed" in low:
            code = 403
        else:
            code = 400
        raise HTTPException(status_code=code, detail=msg) from e


@router.patch("/{instance_id}/advance")
async def advance_flow_instance_route(
    tenant_database: str,
    instance_id: str,
    body: FlowInstanceAdvance = Body(default_factory=FlowInstanceAdvance),
    user=Depends(require_user_same_tenant),
):
    try:
        payload = body.payload
        inst = flow_instance_service.advance_flow_instance(
            tenant_database,
            instance_id,
            payload=payload,
            acting_user=user,
        )
        return {"message": "Flow instance updated", "instance": inst}
    except ValueError as e:
        msg = str(e)
        low = msg.lower()
        if "not allowed" in low:
            raise HTTPException(status_code=403, detail=msg) from e
        raise HTTPException(status_code=400, detail=msg) from e


@router.patch("/{instance_id}/end")
async def end_flow_instance_route(
    tenant_database: str,
    instance_id: str,
    user=Depends(require_user_same_tenant),
):
    try:
        inst = flow_instance_service.end_flow_instance_by_user(
            tenant_database,
            instance_id,
            acting_user=user,
        )
        return {"message": "Flow instance ended", "instance": inst}
    except ValueError as e:
        msg = str(e)
        low = msg.lower()
        if "not found" in low:
            code = 404
        elif "not allowed" in low:
            code = 403
        else:
            code = 400
        raise HTTPException(status_code=code, detail=msg) from e
