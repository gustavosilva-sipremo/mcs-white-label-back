from fastapi import APIRouter, HTTPException, Depends

from app.dependencies.auth_dependency import require_admin_same_tenant
from app.models.questionnaire import QuestionnaireCreate, QuestionnaireUpdate
from app.services.questionnaire_service import (
    list_questionnaires,
    create_questionnaire,
    get_questionnaire_by_id,
    update_questionnaire,
    delete_questionnaire,
)

router = APIRouter(
    prefix="/{tenant_database}/questionnaires",
    tags=["Tenant Questionnaires"],
)


@router.get("")
async def list_questionnaires_route(
    tenant_database: str,
    _admin=Depends(require_admin_same_tenant),
):
    try:
        items = list_questionnaires(tenant_database)
        return {"tenant": tenant_database, "questionnaires": items}
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def create_questionnaire_route(
    tenant_database: str,
    body: QuestionnaireCreate,
    _admin=Depends(require_admin_same_tenant),
):
    try:
        doc = create_questionnaire(
            tenant_database,
            body.model_dump(exclude_none=True),
        )
        return {"message": "Questionnaire created successfully", "questionnaire": doc}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{questionnaire_id}")
async def get_questionnaire_route(
    tenant_database: str,
    questionnaire_id: str,
    _admin=Depends(require_admin_same_tenant),
):
    try:
        return get_questionnaire_by_id(tenant_database, questionnaire_id)
    except ValueError as e:
        msg = str(e)
        code = 404 if "not found" in msg.lower() or "invalid" in msg.lower() else 400
        raise HTTPException(status_code=code, detail=msg)


@router.patch("/{questionnaire_id}")
async def patch_questionnaire_route(
    tenant_database: str,
    questionnaire_id: str,
    body: QuestionnaireUpdate,
    _admin=Depends(require_admin_same_tenant),
):
    try:
        return update_questionnaire(
            tenant_database,
            questionnaire_id,
            body.model_dump(exclude_unset=True),
        )
    except ValueError as e:
        msg = str(e)
        code = 404 if "not found" in msg.lower() else 400
        raise HTTPException(status_code=code, detail=msg)


@router.delete("/{questionnaire_id}")
async def delete_questionnaire_route(
    tenant_database: str,
    questionnaire_id: str,
    _admin=Depends(require_admin_same_tenant),
):
    try:
        return delete_questionnaire(tenant_database, questionnaire_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
