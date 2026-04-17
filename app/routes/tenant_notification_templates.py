from fastapi import APIRouter, HTTPException, Depends

from app.dependencies.auth_dependency import require_admin_same_tenant
from app.models.notification_template import (
    NotificationTemplateCreate,
    NotificationTemplateUpdate,
    NotificationPreviewBody,
)
from app.services.notification_template_service import (
    list_notification_templates,
    create_notification_template,
    get_notification_template_by_id,
    update_notification_template,
    delete_notification_template,
    preview_notification_templates,
    test_pwa_payload,
)

router = APIRouter(
    prefix="/{tenant_database}/notification-templates",
    tags=["Tenant Notification Templates"],
)


@router.get("")
async def list_templates_route(
    tenant_database: str,
    _admin=Depends(require_admin_same_tenant),
):
    try:
        items = list_notification_templates(tenant_database)
        return {"tenant": tenant_database, "templates": items}
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def create_template_route(
    tenant_database: str,
    body: NotificationTemplateCreate,
    _admin=Depends(require_admin_same_tenant),
):
    try:
        doc = create_notification_template(
            tenant_database,
            body.model_dump(exclude_none=True),
        )
        return {"message": "Template created successfully", "template": doc}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/preview")
async def preview_template_route(
    tenant_database: str,
    body: NotificationPreviewBody,
    _admin=Depends(require_admin_same_tenant),
):
    try:
        return preview_notification_templates(
            body.header_template,
            body.body_template,
            body.footer_template,
            body.sms_template,
            preview_title=body.preview_title,
            brand_primary=body.brand_primary,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{template_id}")
async def get_template_route(
    tenant_database: str,
    template_id: str,
    _admin=Depends(require_admin_same_tenant),
):
    try:
        return get_notification_template_by_id(tenant_database, template_id)
    except ValueError as e:
        msg = str(e)
        code = 404 if "not found" in msg.lower() or "invalid" in msg.lower() else 400
        raise HTTPException(status_code=code, detail=msg)


@router.patch("/{template_id}")
async def patch_template_route(
    tenant_database: str,
    template_id: str,
    body: NotificationTemplateUpdate,
    _admin=Depends(require_admin_same_tenant),
):
    try:
        return update_notification_template(
            tenant_database,
            template_id,
            body.model_dump(exclude_unset=True),
        )
    except ValueError as e:
        msg = str(e)
        code = 404 if "not found" in msg.lower() else 400
        raise HTTPException(status_code=code, detail=msg)


@router.delete("/{template_id}")
async def delete_template_route(
    tenant_database: str,
    template_id: str,
    _admin=Depends(require_admin_same_tenant),
):
    try:
        return delete_notification_template(tenant_database, template_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{template_id}/test-pwa")
async def test_pwa_route(
    tenant_database: str,
    template_id: str,
    _admin=Depends(require_admin_same_tenant),
):
    try:
        return test_pwa_payload(tenant_database, template_id)
    except ValueError as e:
        msg = str(e)
        code = 404 if "not found" in msg.lower() else 400
        raise HTTPException(status_code=code, detail=msg)
