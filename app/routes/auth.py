from fastapi import APIRouter, HTTPException, Depends, Request, Query
from pydantic import BaseModel, Field

from app.dependencies.auth_dependency import get_current_user, get_admin_user

from app.services.auth_service import (
    login_user,
    refresh_access_token,
    logout_user,
    update_logged_user_terms,
)
from app.services.tenant_service import (
    list_active_tenants_for_login,
    resolve_public_tenant_features,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


# =========================
# Schemas
# =========================
class LoginRequest(BaseModel):
    tenant_db: str = Field(..., example="sipremo")
    username: str = Field(..., example="gustavo")
    password: str = Field(..., example="123456")


class RefreshRequest(BaseModel):
    refresh_token: str


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str
    expires_in: int


class TermItem(BaseModel):
    name: str
    value: bool


class UpdateTermsRequest(BaseModel):
    terms: list[TermItem]
    required_term_names: list[str] = Field(default_factory=list)


# =========================
# Tenants for login (public)
# =========================
@router.get("/login-tenants")
async def login_tenants():
    """
    Lista empresas ativas para seleção na tela de login.
    Não requer autenticação.
    """

    try:
        return {"tenants": list_active_tenants_for_login()}
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


# =========================
# Public tenant features (no auth)
# =========================
@router.get("/public-features")
async def public_tenant_features(
    request: Request,
    tenant_db: str | None = Query(
        None,
        description="Opcional: database do tenant (ex.: dev quando Host não bate em domains).",
    ),
):
    """
    Features para gating de rotas públicas (/public-maps, /public-occurrence-trigger).
    Resolve por tenant_db ou pelo header Host (domínios cadastrados no tenant).
    """

    try:
        host = request.headers.get("host")
        features = resolve_public_tenant_features(host, tenant_db)
        return {"features": features}
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


# =========================
# Login
# =========================
@router.post("/login", response_model=TokenResponse)
async def login(data: LoginRequest):
    """
    Realiza login do usuário
    """

    try:
        return login_user(data.model_dump())

    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


# =========================
# Refresh Token
# =========================
@router.post("/refresh", response_model=TokenResponse)
async def refresh(data: RefreshRequest):
    """
    Gera novo access token usando refresh token
    """

    try:
        return refresh_access_token(data.refresh_token)

    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


# =========================
# Logout
# =========================
@router.post("/logout")
async def logout(data: LogoutRequest):
    """
    Revoga refresh token
    """

    try:
        return logout_user(data.refresh_token)

    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


@router.patch("/terms")
async def update_my_terms(
    data: UpdateTermsRequest,
    current_user=Depends(get_current_user),
):
    """
    Atualiza os termos do usuário autenticado.
    Valida apenas os termos obrigatórios informados em required_term_names.
    """
    try:
        user = update_logged_user_terms(
            tenant_db=current_user.get("tenant_database"),
            user_id=current_user.get("_id"),
            terms=[term.model_dump() for term in data.terms],
            required_term_names=data.required_term_names,
        )
        return {"message": "Terms updated successfully", "user": user}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")


# =========================
# Protected Route (any user)
# =========================
@router.get("/protected-user")
async def protected_user(current_user=Depends(get_current_user)):
    """
    Rota protegida que requer apenas autenticação
    """

    return {
        "message": "Access granted",
        "user": current_user,
    }


# =========================
# Protected Route (admin)
# =========================
@router.get("/protected-admin")
async def protected_admin(admin_user=Depends(get_admin_user)):
    """
    Rota protegida apenas para admin
    """

    return {
        "message": "Admin access granted",
        "user": admin_user,
    }
