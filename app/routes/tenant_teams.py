from fastapi import APIRouter, HTTPException, Depends

from app.dependencies.auth_dependency import require_admin_same_tenant
from app.models.team import TeamCreate, TeamUpdate
from app.services.team_service import (
    list_teams,
    create_team,
    get_team_by_id,
    update_team,
    delete_team,
)

router = APIRouter(prefix="/{tenant_database}/teams", tags=["Tenant Teams"])


@router.get("")
async def list_teams_route(
    tenant_database: str,
    _admin=Depends(require_admin_same_tenant),
):
    try:
        teams = list_teams(tenant_database)
        return {"tenant": tenant_database, "teams": teams}
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def create_team_route(
    tenant_database: str,
    body: TeamCreate,
    _admin=Depends(require_admin_same_tenant),
):
    try:
        team = create_team(tenant_database, body.model_dump(exclude_none=True))
        return {"message": "Team created successfully", "team": team}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/{team_id}")
async def get_team_route(
    tenant_database: str,
    team_id: str,
    _admin=Depends(require_admin_same_tenant),
):
    try:
        return get_team_by_id(tenant_database, team_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.patch("/{team_id}")
async def patch_team_route(
    tenant_database: str,
    team_id: str,
    body: TeamUpdate,
    _admin=Depends(require_admin_same_tenant),
):
    try:
        return update_team(tenant_database, team_id, body.model_dump(exclude_unset=True))
    except ValueError as e:
        msg = str(e)
        code = 404 if "not found" in msg.lower() else 400
        raise HTTPException(status_code=code, detail=msg)


@router.delete("/{team_id}")
async def delete_team_route(
    tenant_database: str,
    team_id: str,
    _admin=Depends(require_admin_same_tenant),
):
    try:
        return delete_team(tenant_database, team_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
