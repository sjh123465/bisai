"""认证与权限体系 — 零依赖实现（PBKDF2 口令哈希 + HMAC 签名 Token）

- 用户存储: data/users.json
- 角色: student / teacher
- Token: base64(payload).hmac_sha256(payload)，有效期默认 24h
- 依赖注入: get_current_user / require_role
"""
import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Optional

from fastapi import Depends, HTTPException, Request
from app.core.config import get_settings
from app.core.logger import get_logger

logger = get_logger("auth")

TOKEN_TTL_SECONDS = 24 * 3600

# 首次启动自动创建的演示账号（答辩用，正式环境应删除）
DEFAULT_ACCOUNTS = {
    "teacher": {"password": "123456", "role": "teacher", "display_name": "王老师"},
    "student": {"password": "123456", "role": "student", "display_name": "演示学生"},
}


# ---------------- 口令哈希（PBKDF2-HMAC-SHA256, 120k 迭代） ----------------

def hash_password(password: str, salt: Optional[str] = None) -> dict:
    salt = salt or secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 120_000)
    return {"salt": salt, "hash": dk.hex()}


def verify_password(password: str, stored: dict) -> bool:
    try:
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), stored["salt"].encode(), 120_000)
        return hmac.compare_digest(dk.hex(), stored["hash"])
    except Exception:
        return False


# ---------------- Token（HMAC 签名，无状态） ----------------

def _secret() -> str:
    cfg = get_settings()
    return cfg.auth_secret or "codementor-dev-secret-change-me"


def create_token(username: str, role: str) -> str:
    payload = json.dumps({"u": username, "r": role, "exp": int(time.time()) + TOKEN_TTL_SECONDS})
    raw = base64.urlsafe_b64encode(payload.encode()).decode()
    sig = hmac.new(_secret().encode(), raw.encode(), hashlib.sha256).hexdigest()
    return f"{raw}.{sig}"


def decode_token(token: str) -> Optional[dict]:
    try:
        raw, sig = token.rsplit(".", 1)
        expect = hmac.new(_secret().encode(), raw.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expect):
            return None
        payload = json.loads(base64.urlsafe_b64decode(raw.encode()))
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


# ---------------- 用户存储 ----------------

class UserStore:
    def __init__(self, data_dir: str):
        self.file = os.path.join(data_dir, "users.json")
        self._users: dict = {}
        self._load()

    def _load(self):
        if os.path.exists(self.file):
            try:
                with open(self.file, "r", encoding="utf-8") as f:
                    self._users = json.load(f)
            except Exception as e:
                logger.error(f"用户库加载失败: {e}")
        # 首次启动播种演示账号
        if not self._users:
            for name, info in DEFAULT_ACCOUNTS.items():
                self._users[name] = {
                    **hash_password(info["password"]),
                    "role": info["role"],
                    "display_name": info["display_name"],
                    "created_at": int(time.time()),
                }
            self.save()
            logger.info("👤 已创建演示账号: teacher/123456, student/123456")

    def save(self):
        os.makedirs(os.path.dirname(self.file), exist_ok=True)
        with open(self.file, "w", encoding="utf-8") as f:
            json.dump(self._users, f, ensure_ascii=False, indent=2)

    def get(self, username: str) -> Optional[dict]:
        return self._users.get(username)

    def create(self, username: str, password: str, role: str = "student") -> dict:
        if username in self._users:
            raise ValueError("用户名已存在")
        if not (2 <= len(username) <= 32) or not (6 <= len(password) <= 64):
            raise ValueError("用户名 2-32 字符，密码 6-64 字符")
        if role not in ("student", "teacher"):
            raise ValueError("角色仅支持 student/teacher")
        user = {
            **hash_password(password),
            "role": role,
            "display_name": username,
            "created_at": int(time.time()),
        }
        self._users[username] = user
        self.save()
        return user

    def verify(self, username: str, password: str) -> Optional[dict]:
        u = self._users.get(username)
        if u and verify_password(password, u):
            return u
        return None


_store: Optional[UserStore] = None


def get_user_store() -> UserStore:
    global _store
    if _store is None:
        _store = UserStore(get_settings().data_dir)
    return _store


# ---------------- FastAPI 依赖 ----------------

def get_current_user(request: Request) -> dict:
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="未登录，请先认证")
    payload = decode_token(auth[7:])
    if not payload:
        raise HTTPException(status_code=401, detail="登录已过期或 Token 无效")
    user = get_user_store().get(payload["u"])
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return {"username": payload["u"], "role": payload["r"]}


def require_role(*roles: str):
    """角色守卫: Depends(require_role("teacher"))"""
    async def checker(user: dict = Depends(get_current_user)) -> dict:
        if roles and user["role"] not in roles:
            raise HTTPException(status_code=403, detail=f"需要 {'/'.join(roles)} 权限")
        return user
    return checker
