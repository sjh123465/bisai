"""认证路由 — 注册 / 登录 / 当前用户"""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.security import get_user_store, create_token, get_current_user

router = APIRouter(prefix="/api/auth", tags=["认证"])


class Credentials(BaseModel):
    username: str
    password: str
    role: str = "student"  # 仅注册时用


@router.post("/register")
async def register(body: Credentials):
    try:
        user = get_user_store().create(body.username.strip(), body.password, body.role)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {
        "token": create_token(body.username.strip(), user["role"]),
        "username": body.username.strip(),
        "role": user["role"],
    }


@router.post("/login")
async def login(body: Credentials):
    user = get_user_store().verify(body.username.strip(), body.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return {
        "token": create_token(body.username.strip(), user["role"]),
        "username": body.username.strip(),
        "role": user["role"],
        "display_name": user.get("display_name", body.username),
    }


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return user
