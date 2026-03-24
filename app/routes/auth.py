from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field

from app.dependencies.auth_dependency import get_current_user, get_admin_user

from app.services.auth_service import (
    login_user,
    refresh_access_token,
    logout_user,
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
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str | None = None
    token_type: str
    expires_in: int


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
