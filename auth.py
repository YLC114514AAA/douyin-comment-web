"""
海森堡抖音评论查询 — 用户认证模块
SQLite + SHA256盐值加密 + 邮箱验证码 + Token管理
"""

import hashlib
import json
import os
import random
import smtplib
import sqlite3
import threading
import time
import uuid
from email.mime.text import MIMEText
from functools import wraps
from datetime import datetime, timezone, timedelta

from fastapi import Request
from fastapi.responses import JSONResponse

# ── 数据库 ──
_DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "users.db")
_lock = threading.Lock()


def _get_db() -> sqlite3.Connection:
    db = sqlite3.connect(_DB_PATH, check_same_thread=False)
    db.row_factory = sqlite3.Row
    return db


def init_db():
    db = _get_db()
    db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS verifications (
            email TEXT PRIMARY KEY,
            code TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            salt TEXT NOT NULL,
            expires_at REAL NOT NULL
        )
    """)
    db.commit()
    db.close()


# ── 密码加密 ──

def _hash_password(password: str, salt: str = None) -> tuple[str, str]:
    if salt is None:
        salt = uuid.uuid4().hex
    h = hashlib.sha256((password + salt).encode("utf-8")).hexdigest()
    return h, salt


# ── SMTP 发邮件 ──

def _load_email_config() -> dict:
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "email_config.json")
    if not os.path.exists(cfg_path):
        raise RuntimeError("email_config.json 不存在，请先配置SMTP信息")
    with open(cfg_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _send_verification_code(to_email: str, code: str):
    cfg = _load_email_config()
    msg = MIMEText(
        f"【海森堡抖音评论查询】\n\n"
        f"您的验证码是：{code}\n"
        f"有效期 5 分钟，请勿泄露给他人。\n\n"
        f"如非本人操作，请忽略此邮件。",
        "plain", "utf-8",
    )
    msg["Subject"] = "海森堡 — 邮箱验证码"
    msg["From"] = cfg["sender_email"]
    msg["To"] = to_email

    try:
        server = smtplib.SMTP(cfg["smtp_host"], cfg["smtp_port"], timeout=10)
        server.starttls()
        server.login(cfg["sender_email"], cfg["sender_password"])
        server.sendmail(cfg["sender_email"], [to_email], msg.as_string())
        server.quit()
    except Exception as e:
        raise RuntimeError(f"邮件发送失败: {e}")


# ── Token ──

def _create_token(user_id: int) -> str:
    token = uuid.uuid4().hex
    db = _get_db()
    db.execute(
        "INSERT INTO tokens (user_id, token, created_at) VALUES (?, ?, ?)",
        (user_id, token, datetime.now(timezone(timedelta(hours=8))).isoformat()),
    )
    db.commit()
    db.close()
    return token


def _get_user_by_token(token: str) -> dict | None:
    db = _get_db()
    row = db.execute(
        "SELECT u.id, u.email FROM users u "
        "JOIN tokens t ON u.id = t.user_id "
        "WHERE t.token = ?", (token,)
    ).fetchone()
    db.close()
    if row:
        return {"id": row["id"], "email": row["email"]}
    return None


def _delete_token(token: str):
    db = _get_db()
    db.execute("DELETE FROM tokens WHERE token = ?", (token,))
    db.commit()
    db.close()


# ── 中间件 ──

def require_auth(handler):
    """装饰器：校验请求的 Authorization Bearer token"""
    @wraps(handler)
    async def wrapper(request: Request, *args, **kwargs):
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse({"error": "未登录"}, status_code=401)
        token = auth_header[7:]
        user = _get_user_by_token(token)
        if not user:
            return JSONResponse({"error": "登录已过期，请重新登录"}, status_code=401)
        # 把用户信息挂在 request.state 上
        request.state.user = user
        return await handler(request, *args, **kwargs)
    return wrapper


# ── API 路由（供 server.py 注册） ──

def register_auth_routes(app):
    init_db()

    @app.post("/auth/register/step1")
    async def register_step1(request: Request):
        """输入邮箱+密码，发送验证码"""
        body = await request.json()
        email = (body.get("email") or "").strip().lower()
        password = (body.get("password") or "").strip()

        if not email or "@" not in email or "." not in email:
            return JSONResponse({"error": "请输入有效的邮箱地址"}, status_code=400)
        if len(password) < 6:
            return JSONResponse({"error": "密码至少 6 位"}, status_code=400)

        # 检查邮箱是否已注册
        db = _get_db()
        existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if existing:
            return JSONResponse({"error": "该邮箱已注册，请直接登录"}, status_code=400)

        # 生成验证码 + 暂存密码
        code = str(random.randint(100000, 999999))
        password_hash, salt = _hash_password(password)

        expires_at = time.time() + 300  # 5 分钟
        db.execute(
            "INSERT OR REPLACE INTO verifications (email, code, password_hash, salt, expires_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (email, code, password_hash, salt, expires_at),
        )
        db.commit()
        db.close()

        # 发邮件
        try:
            _send_verification_code(email, code)
        except RuntimeError as e:
            return JSONResponse({"error": str(e)}, status_code=500)

        return JSONResponse({"ok": True, "message": "验证码已发送到您的邮箱"})

    @app.post("/auth/register/step2")
    async def register_step2(request: Request):
        """输入邮箱+验证码，完成注册"""
        body = await request.json()
        email = (body.get("email") or "").strip().lower()
        code = (body.get("code") or "").strip()

        if not email or not code:
            return JSONResponse({"error": "请输入邮箱和验证码"}, status_code=400)

        db = _get_db()
        row = db.execute(
            "SELECT code, password_hash, salt, expires_at FROM verifications WHERE email = ?",
            (email,),
        ).fetchone()

        if not row:
            return JSONResponse({"error": "请先获取验证码"}, status_code=400)
        if time.time() > row["expires_at"]:
            db.execute("DELETE FROM verifications WHERE email = ?", (email,))
            db.commit()
            db.close()
            return JSONResponse({"error": "验证码已过期，请重新获取"}, status_code=400)
        if row["code"] != code:
            return JSONResponse({"error": "验证码错误"}, status_code=400)

        # 创建用户
        db.execute(
            "INSERT INTO users (email, password_hash, salt, created_at) VALUES (?, ?, ?, ?)",
            (email, row["password_hash"], row["salt"],
             datetime.now(timezone(timedelta(hours=8))).isoformat()),
        )
        db.execute("DELETE FROM verifications WHERE email = ?", (email,))
        db.commit()

        # 获取新用户 ID 并创建 token
        user = db.execute("SELECT id, email FROM users WHERE email = ?", (email,)).fetchone()
        db.close()

        token = _create_token(user["id"])
        return JSONResponse({"ok": True, "token": token, "email": email})

    @app.post("/auth/login")
    async def login(request: Request):
        """邮箱+密码登录"""
        body = await request.json()
        email = (body.get("email") or "").strip().lower()
        password = (body.get("password") or "").strip()

        if not email or not password:
            return JSONResponse({"error": "请输入邮箱和密码"}, status_code=400)

        db = _get_db()
        user = db.execute(
            "SELECT id, email, password_hash, salt FROM users WHERE email = ?",
            (email,),
        ).fetchone()
        db.close()

        if not user:
            return JSONResponse({"error": "邮箱或密码错误"}, status_code=400)

        h, _ = _hash_password(password, user["salt"])
        if h != user["password_hash"]:
            return JSONResponse({"error": "邮箱或密码错误"}, status_code=400)

        token = _create_token(user["id"])
        return JSONResponse({"ok": True, "token": token, "email": email})

    @app.post("/auth/logout")
    async def logout(request: Request):
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            _delete_token(auth_header[7:])
        return JSONResponse({"ok": True})

    @app.get("/auth/me")
    async def me(request: Request):
        """获取当前登录用户信息"""
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse({"error": "未登录"}, status_code=401)
        user = _get_user_by_token(auth_header[7:])
        if not user:
            return JSONResponse({"error": "登录已过期"}, status_code=401)
        return JSONResponse({"ok": True, "user": user})
