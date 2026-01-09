"""Authentication API routes"""
from fastapi import APIRouter, HTTPException, Depends, Request, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, validator
from typing import Optional
import re

from app.auth import (
    create_user, authenticate_user, create_session,
    verify_session, invalidate_session, create_jwt_token, verify_jwt_token
)

router = APIRouter(prefix="/api/auth", tags=["auth"])
security = HTTPBearer(auto_error=False)

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str

    @validator('password')
    def password_strength(cls, v):
        if len(v) < 8:
            raise ValueError('Password must be at least 8 characters')
        if not re.search(r'[A-Za-z]', v):
            raise ValueError('Password must contain letters')
        if not re.search(r'[0-9]', v):
            raise ValueError('Password must contain numbers')
        return v

class LoginRequest(BaseModel):
    email: EmailStr
    password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict

class MessageResponse(BaseModel):
    message: str

async def get_current_user(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)
) -> Optional[dict]:
    """Get current user from session token or JWT"""
    # Try Authorization header first
    if credentials:
        token = credentials.credentials
        # Try JWT
        user = verify_jwt_token(token)
        if user:
            return {"id": user["sub"], "email": user["email"]}
        # Try session token
        user = verify_session(token)
        if user:
            return user

    # Try cookie
    session_token = request.cookies.get("session_token")
    if session_token:
        user = verify_session(session_token)
        if user:
            return user

    return None

async def require_auth(user: Optional[dict] = Depends(get_current_user)) -> dict:
    """Require authenticated user"""
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user

@router.post("/register", response_model=TokenResponse)
async def register(request: Request, data: RegisterRequest, response: Response):
    """Register new user"""
    user = create_user(data.email, data.password)
    if not user:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Create session
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    session_token = create_session(str(user["id"]), ip, ua)

    # Also create JWT for API usage
    jwt_token = create_jwt_token(str(user["id"]), user["email"])

    # Set cookie
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=86400
    )

    return TokenResponse(
        access_token=jwt_token,
        user={"id": str(user["id"]), "email": user["email"], "role": user["role"]}
    )

@router.post("/login", response_model=TokenResponse)
async def login(request: Request, data: LoginRequest, response: Response):
    """Login user"""
    user = authenticate_user(data.email, data.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid credentials")

    # Create session
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent")
    session_token = create_session(user["id"], ip, ua)

    # Create JWT
    jwt_token = create_jwt_token(user["id"], user["email"])

    # Set cookie
    response.set_cookie(
        key="session_token",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=86400
    )

    return TokenResponse(access_token=jwt_token, user=user)

@router.post("/logout", response_model=MessageResponse)
async def logout(request: Request, response: Response):
    """Logout user"""
    session_token = request.cookies.get("session_token")
    if session_token:
        invalidate_session(session_token)

    response.delete_cookie("session_token")
    return MessageResponse(message="Logged out")

@router.get("/me")
async def get_me(user: dict = Depends(require_auth)):
    """Get current user info"""
    return user

@router.get("/verify")
async def verify_auth(user: Optional[dict] = Depends(get_current_user)):
    """Verify if user is authenticated"""
    if user:
        return {"authenticated": True, "user": user}
    return {"authenticated": False, "user": None}
