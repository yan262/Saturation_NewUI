# Login & RBAC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add login page + JWT/LDAP authentication + configurable RBAC to the saturation monitor, with login as the landing page.

**Architecture:** auth.py handles all auth logic (JWT, bcrypt, ldap3, RBAC). An ASGI middleware intercepts `/api/*` requests for JWT + permission checks. login.html is the entry point — successful login stores tokens in localStorage and redirects to index.html (dashboard). Admin panel is embedded in index.html as a hidden overlay.

**Tech Stack:** FastAPI, SQLite, PyJWT, bcrypt, ldap3, vanilla JS frontend

**User Flow:**
```
访问 / → login.html（登录页） → 登录成功 → 跳转 /index.html（仪表板）
                                            │
                          管理员看到"管理"按钮 → 用户/角色管理面板
  
  直接访问 /index.html → 无 token → 跳转 /login.html
```

---

### Task 1: Update config.py and requirements.txt

**Files:**
- Modify: `config.py`
- Modify: `requirements.txt`

- [ ] **Step 1: Add auth config to config.py**

Append the following to `config.py`:

```python
# ============================================================
# 认证配置
# ============================================================
JWT_SECRET = "change-me-to-a-random-secret-string"  # JWT 签名密钥 ★ 生产环境请修改
JWT_ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30    # access token 有效期（分钟）
REFRESH_TOKEN_EXPIRE_DAYS = 7       # refresh token 有效期（天）

# ============================================================
# LDAP/AD 配置（可选，不使用 LDAP 可忽略）
# ============================================================
LDAP_ENABLED = False                # True=启用 LDAP 认证
LDAP_SERVER = "ldap://your-ad-server:389"
LDAP_BASE_DN = "dc=company,dc=com"
LDAP_DOMAIN = "COMPANY"             # AD 域名（用于 user@domain 格式登录）
```

- [ ] **Step 2: Add dependencies to requirements.txt**

Append to `requirements.txt`:

```
pyjwt>=2.8.0
bcrypt>=4.1.0
ldap3>=2.9.0
```

- [ ] **Step 3: Install new dependencies**

Run: `pip install pyjwt bcrypt ldap3`
Expected: All three packages install successfully.

---

### Task 2: Create auth.py

**Files:**
- Create: `auth.py`

- [ ] **Step 1: Write auth.py — db init + password utils + JWT**

```python
"""
认证与 RBAC 模块
===============
JWT 签发/验证、bcrypt 密码哈希、LDAP/AD 认证、角色权限管理。
"""

import sqlite3
import os
from datetime import datetime, timedelta
from functools import wraps

import jwt
import bcrypt
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from fastapi.responses import JSONResponse

# ---- 配置 ----
from config import (
    JWT_SECRET, JWT_ALGORITHM,
    ACCESS_TOKEN_EXPIRE_MINUTES, REFRESH_TOKEN_EXPIRE_DAYS,
    LDAP_ENABLED, LDAP_SERVER, LDAP_BASE_DN, LDAP_DOMAIN,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "saturation.db")

# ---- 预置权限 & 角色 ----
PRESET_PERMISSIONS = [
    ("dashboard:view", "查看仪表板", "查看实时饱和度数据、图表和统计"),
    ("settings:write", "修改监控设置", "修改刷新频率和报警阈值"),
    ("data:export", "导出 CSV", "导出全部历史数据为 CSV 文件"),
    ("users:manage", "用户管理", "创建、编辑、删除用户"),
    ("roles:manage", "角色权限管理", "创建角色、分配权限"),
    ("alarms:view", "查看报警日志", "查看报警历史记录"),
]

PRESET_ROLES = {
    "超级管理员": ["dashboard:view", "settings:write", "data:export",
                   "users:manage", "roles:manage", "alarms:view"],
    "运维工程师": ["dashboard:view", "settings:write", "data:export", "alarms:view"],
    "只读用户":   ["dashboard:view", "alarms:view"],
}

ROUTE_PERMISSIONS = {
    # 现有 API
    ("GET", "/api/saturation/current"):  "dashboard:view",
    ("GET", "/api/saturation/history"):  "dashboard:view",
    ("GET", "/api/saturation/stats"):    "dashboard:view",
    ("GET", "/api/alarm/logs"):          "alarms:view",
    ("GET", "/api/export/csv"):          "data:export",
    ("PUT", "/api/settings"):            "settings:write",
    ("GET", "/api/settings"):            "dashboard:view",
    # 管理 API
    ("GET",  "/api/users"):              "users:manage",
    ("POST", "/api/users"):              "users:manage",
    ("PUT", "/api/users/{id}"):          "users:manage",
    ("DELETE", "/api/users/{id}"):       "users:manage",
    ("GET",  "/api/roles"):              "roles:manage",
    ("POST", "/api/roles"):              "roles:manage",
    ("PUT", "/api/roles/{id}"):          "roles:manage",
    ("DELETE", "/api/roles/{id}"):       "roles:manage",
    ("GET",  "/api/permissions"):        "roles:manage",
}


# ============================================================
# 数据库初始化
# ============================================================
def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_auth_db():
    """建表 + 预置数据 + 默认管理员（首次启动调用）。"""
    conn = _get_db()
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT,
        display_name TEXT DEFAULT '',
        auth_type TEXT DEFAULT 'local',
        ldap_dn TEXT,
        is_active INTEGER DEFAULT 1,
        last_login TEXT,
        created_at TEXT NOT NULL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS roles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        description TEXT DEFAULT '',
        is_system INTEGER DEFAULT 0,
        created_at TEXT NOT NULL
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS permissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        description TEXT DEFAULT ''
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS user_roles (
        user_id INTEGER NOT NULL,
        role_id INTEGER NOT NULL,
        PRIMARY KEY (user_id, role_id),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS role_permissions (
        role_id INTEGER NOT NULL,
        permission_id INTEGER NOT NULL,
        PRIMARY KEY (role_id, permission_id),
        FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
        FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE
    )""")

    # 插入预置权限（跳过已存在的）
    for code, name, desc in PRESET_PERMISSIONS:
        c.execute("INSERT OR IGNORE INTO permissions (code, name, description) VALUES (?, ?, ?)",
                  (code, name, desc))

    # 权限 code → id 映射
    perm_map = {}
    c.execute("SELECT id, code FROM permissions")
    for row in c.fetchall():
        perm_map[row["code"]] = row["id"]

    # 插入预置角色
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for role_name, perm_codes in PRESET_ROLES.items():
        c.execute("INSERT OR IGNORE INTO roles (name, description, is_system, created_at) VALUES (?, ?, 1, ?)",
                  (role_name, role_name, now))
        c.execute("SELECT id FROM roles WHERE name = ?", (role_name,))
        role_id = c.fetchone()["id"]
        for code in perm_codes:
            if code in perm_map:
                c.execute("INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
                          (role_id, perm_map[code]))

    # 默认管理员 admin / admin123（密码仅首次创建时设置）
    c.execute("SELECT id FROM users WHERE username = 'admin'")
    if not c.fetchone():
        pw_hash = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode()
        c.execute("""INSERT INTO users (username, password_hash, display_name, auth_type, created_at)
                     VALUES ('admin', ?, '管理员', 'local', ?)""", (pw_hash, now))
        c.execute("SELECT id FROM users WHERE username = 'admin'")
        uid = c.fetchone()["id"]
        c.execute("SELECT id FROM roles WHERE name = '超级管理员'")
        rid = c.fetchone()["id"]
        c.execute("INSERT INTO user_roles (user_id, role_id) VALUES (?, ?)", (uid, rid))

    conn.commit()
    conn.close()


# ============================================================
# 密码工具
# ============================================================
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


# ============================================================
# JWT 工具
# ============================================================
def create_access_token(user_id: int, username: str) -> str:
    payload = {
        "sub": str(user_id),
        "username": username,
        "type": "access",
        "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: int, username: str) -> str:
    payload = {
        "sub": str(user_id),
        "username": username,
        "type": "refresh",
        "exp": datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict:
    """验证 token，返回 payload。无效/过期抛出 HTTPException。"""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token 已过期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="token 无效")


# ============================================================
# LDAP 认证
# ============================================================
def ldap_authenticate(username: str, password: str) -> bool:
    """尝试 LDAP/AD 绑定验证。成功返回 True，失败返回 False。"""
    if not LDAP_ENABLED:
        return False
    try:
        from ldap3 import Server, Connection, ALL
        server = Server(LDAP_SERVER, get_info=ALL, connect_timeout=5)
        user_dn = f"{username}@{LDAP_DOMAIN}"
        conn = Connection(server, user=user_dn, password=password, auto_bind=True)
        conn.unbind()
        return True
    except Exception:
        return False


# ============================================================
# 权限查询
# ============================================================
def get_user_permissions(user_id: int) -> set:
    """返回用户拥有的所有权限码集合。"""
    conn = _get_db()
    c = conn.cursor()
    c.execute("""
        SELECT DISTINCT p.code FROM permissions p
        JOIN role_permissions rp ON p.id = rp.permission_id
        JOIN user_roles ur ON rp.role_id = ur.role_id
        WHERE ur.user_id = ?
    """, (user_id,))
    perms = {row["code"] for row in c.fetchall()}
    conn.close()
    return perms


def require_permission(code: str):
    """FastAPI 依赖注入：检查当前用户是否拥有指定权限。"""
    def checker(request: Request):
        user_perms = getattr(request.state, "user_permissions", set())
        if code not in user_perms:
            raise HTTPException(status_code=403, detail=f"需要权限: {code}")
    return Depends(checker)


# ============================================================
# Auth 路由 (/api/auth/*)
# ============================================================
auth_router = APIRouter(prefix="/api/auth", tags=["认证"])


@auth_router.post("/login")
def login(payload: dict):
    username = payload.get("username", "").strip()
    password = payload.get("password", "")
    auth_type = payload.get("auth_type", "local")

    if not username or not password:
        raise HTTPException(status_code=400, detail="用户名和密码不能为空")

    conn = _get_db()
    c = conn.cursor()
    user = None

    if auth_type == "ldap":
        # LDAP 认证：先查本地是否有该用户记录
        if ldap_authenticate(username, password):
            c.execute("SELECT * FROM users WHERE username = ? AND is_active = 1", (username,))
            row = c.fetchone()
            if row:
                user = dict(row)
        if not user:
            raise HTTPException(status_code=401, detail="用户名或密码错误")
    else:
        # 本地认证
        c.execute("SELECT * FROM users WHERE username = ? AND auth_type = 'local' AND is_active = 1",
                  (username,))
        row = c.fetchone()
        if row and verify_password(password, row["password_hash"]):
            user = dict(row)
        else:
            raise HTTPException(status_code=401, detail="用户名或密码错误")

    # 更新最后登录时间
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("UPDATE users SET last_login = ? WHERE id = ?", (now, user["id"]))
    conn.commit()
    conn.close()

    access = create_access_token(user["id"], user["username"])
    refresh = create_refresh_token(user["id"], user["username"])
    perms = get_user_permissions(user["id"])

    return {
        "access_token": access,
        "refresh_token": refresh,
        "user": {
            "id": user["id"],
            "username": user["username"],
            "display_name": user["display_name"],
            "auth_type": user["auth_type"],
            "permissions": sorted(perms),
        }
    }


@auth_router.post("/refresh")
def refresh(payload: dict):
    token = payload.get("refresh_token", "")
    if not token:
        raise HTTPException(status_code=400, detail="缺少 refresh_token")

    try:
        data = verify_token(token)
        if data.get("type") != "refresh":
            raise HTTPException(status_code=401, detail="token 类型错误")
    except HTTPException:
        raise HTTPException(status_code=401, detail="refresh_token 无效或已过期")

    user_id = int(data["sub"])
    username = data["username"]

    # 确认用户仍存在且启用
    conn = _get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM users WHERE id = ? AND is_active = 1", (user_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(status_code=403, detail="账号已被禁用")
    conn.close()

    return {"access_token": create_access_token(user_id, username)}


@auth_router.get("/me")
def me(request: Request):
    """返回当前登录用户信息。需要鉴权（由中间件保证）。"""
    user_id = int(request.state.user_id)
    conn = _get_db()
    c = conn.cursor()
    c.execute("SELECT id, username, display_name, auth_type, last_login, created_at FROM users WHERE id = ?",
              (user_id,))
    row = c.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="用户不存在")
    perms = get_user_permissions(user_id)
    return {**dict(row), "permissions": sorted(perms)}


@auth_router.put("/password")
def change_password(payload: dict, request: Request):
    """修改自己的密码（仅本地账号）。"""
    old_pw = payload.get("old_password", "")
    new_pw = payload.get("new_password", "")

    if not new_pw or len(new_pw) < 4:
        raise HTTPException(status_code=400, detail="新密码至少 4 位")

    user_id = int(request.state.user_id)
    conn = _get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = c.fetchone()
    if not row or row["auth_type"] != "local":
        conn.close()
        raise HTTPException(status_code=400, detail="LDAP 账号不支持修改密码")

    if not verify_password(old_pw, row["password_hash"]):
        conn.close()
        raise HTTPException(status_code=400, detail="原密码错误")

    c.execute("UPDATE users SET password_hash = ? WHERE id = ?",
              (hash_password(new_pw), user_id))
    conn.commit()
    conn.close()
    return {"message": "密码修改成功"}


# ============================================================
# 管理路由 — 用户管理 (/api/users/*)
# ============================================================
admin_router = APIRouter(prefix="/api", tags=["管理"])


@admin_router.get("/users")
def list_users():
    conn = _get_db()
    c = conn.cursor()
    c.execute("""
        SELECT u.id, u.username, u.display_name, u.auth_type, u.is_active, u.last_login, u.created_at,
               GROUP_CONCAT(r.name) AS role_names,
               GROUP_CONCAT(r.id) AS role_ids
        FROM users u
        LEFT JOIN user_roles ur ON u.id = ur.user_id
        LEFT JOIN roles r ON ur.role_id = r.id
        GROUP BY u.id
        ORDER BY u.id
    """)
    users = []
    for row in c.fetchall():
        u = dict(row)
        u["is_active"] = bool(u["is_active"])
        u["role_names"] = u["role_names"].split(",") if u["role_names"] else []
        u["role_ids"] = [int(x) for x in u["role_ids"].split(",")] if u["role_ids"] else []
        u.pop("password_hash", None)
        users.append(u)
    conn.close()
    return users


@admin_router.post("/users")
def create_user(payload: dict):
    username = payload.get("username", "").strip()
    password = payload.get("password", "")
    display_name = payload.get("display_name", username)
    auth_type = payload.get("auth_type", "local")
    role_ids = payload.get("role_ids", [])
    is_active = payload.get("is_active", True)

    if not username or (auth_type == "local" and not password):
        raise HTTPException(status_code=400, detail="用户名和密码不能为空")

    conn = _get_db()
    c = conn.cursor()

    c.execute("SELECT id FROM users WHERE username = ?", (username,))
    if c.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="用户名已存在")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    pw_hash = hash_password(password) if auth_type == "local" and password else None
    c.execute("""INSERT INTO users (username, password_hash, display_name, auth_type, is_active, created_at)
                 VALUES (?, ?, ?, ?, ?, ?)""",
              (username, pw_hash, display_name, auth_type, int(is_active), now))
    uid = c.lastrowid

    for rid in role_ids:
        c.execute("INSERT OR IGNORE INTO user_roles (user_id, role_id) VALUES (?, ?)", (uid, rid))

    conn.commit()
    conn.close()
    return {"message": "用户创建成功", "id": uid}


@admin_router.put("/users/{user_id}")
def update_user(user_id: int, payload: dict):
    conn = _get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    if not c.fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="用户不存在")

    if "display_name" in payload:
        c.execute("UPDATE users SET display_name = ? WHERE id = ?",
                  (payload["display_name"], user_id))
    if "is_active" in payload:
        c.execute("UPDATE users SET is_active = ? WHERE id = ?",
                  (int(payload["is_active"]), user_id))
    if "password" in payload and payload["password"]:
        c.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                  (hash_password(payload["password"]), user_id))
    if "role_ids" in payload:
        c.execute("DELETE FROM user_roles WHERE user_id = ?", (user_id,))
        for rid in payload["role_ids"]:
            c.execute("INSERT OR IGNORE INTO user_roles (user_id, role_id) VALUES (?, ?)",
                      (user_id, rid))
    conn.commit()
    conn.close()
    return {"message": "用户更新成功"}


@admin_router.delete("/users/{user_id}")
def delete_user(user_id: int, request: Request):
    if int(request.state.user_id) == user_id:
        raise HTTPException(status_code=400, detail="不能删除自己的账号")

    conn = _get_db()
    c = conn.cursor()
    c.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    return {"message": "用户已删除"}


# ============================================================
# 管理路由 — 角色管理 (/api/roles/*)
# ============================================================
@admin_router.get("/roles")
def list_roles():
    conn = _get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM roles ORDER BY id")
    roles = []
    for row in c.fetchall():
        r = dict(row)
        r["is_system"] = bool(r["is_system"])
        c.execute("""
            SELECT p.id, p.code, p.name FROM permissions p
            JOIN role_permissions rp ON p.id = rp.permission_id
            WHERE rp.role_id = ?
        """, (r["id"],))
        r["permissions"] = [dict(p) for p in c.fetchall()]
        roles.append(r)
    conn.close()
    return roles


@admin_router.post("/roles")
def create_role(payload: dict):
    name = payload.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="角色名不能为空")
    desc = payload.get("description", "")
    perm_ids = payload.get("permission_ids", [])

    conn = _get_db()
    c = conn.cursor()
    c.execute("SELECT id FROM roles WHERE name = ?", (name,))
    if c.fetchone():
        conn.close()
        raise HTTPException(status_code=400, detail="角色名已存在")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    c.execute("INSERT INTO roles (name, description, is_system, created_at) VALUES (?, ?, 0, ?)",
              (name, desc, now))
    rid = c.lastrowid
    for pid in perm_ids:
        c.execute("INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
                  (rid, pid))
    conn.commit()
    conn.close()
    return {"message": "角色创建成功", "id": rid}


@admin_router.put("/roles/{role_id}")
def update_role(role_id: int, payload: dict):
    conn = _get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM roles WHERE id = ?", (role_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="角色不存在")

    if "name" in payload:
        c.execute("UPDATE roles SET name = ? WHERE id = ?", (payload["name"], role_id))
    if "description" in payload:
        c.execute("UPDATE roles SET description = ? WHERE id = ?",
                  (payload["description"], role_id))
    if "permission_ids" in payload:
        c.execute("DELETE FROM role_permissions WHERE role_id = ?", (role_id,))
        for pid in payload["permission_ids"]:
            c.execute("INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
                      (role_id, pid))
    conn.commit()
    conn.close()
    return {"message": "角色更新成功"}


@admin_router.delete("/roles/{role_id}")
def delete_role(role_id: int):
    conn = _get_db()
    c = conn.cursor()
    c.execute("SELECT is_system FROM roles WHERE id = ?", (role_id,))
    row = c.fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="角色不存在")
    if row["is_system"]:
        conn.close()
        raise HTTPException(status_code=400, detail="系统预置角色不可删除")
    c.execute("DELETE FROM roles WHERE id = ?", (role_id,))
    conn.commit()
    conn.close()
    return {"message": "角色已删除"}


@admin_router.get("/permissions")
def list_permissions():
    conn = _get_db()
    c = conn.cursor()
    c.execute("SELECT * FROM permissions ORDER BY id")
    perms = [dict(row) for row in c.fetchall()]
    conn.close()
    return perms


# ============================================================
# ASGI 中间件 — JWT 鉴权 + RBAC
# ============================================================
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse


class AuthMiddleware(BaseHTTPMiddleware):
    """对所有 /api/* 请求进行 JWT 鉴权和 RBAC 权限检查。

    白名单: /api/auth/login, /api/auth/refresh
    其余 /api/* 路径均需携带 Authorization: Bearer <token>
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method

        # 白名单：登录和刷新接口放行
        if path in ("/api/auth/login", "/api/auth/refresh"):
            return await call_next(request)

        # 非 API 路径放行（静态文件等）
        if not path.startswith("/api/"):
            return await call_next(request)

        # 提取并验证 token
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(status_code=401, content={"detail": "缺少认证 token"})

        token = auth_header[7:]
        try:
            payload = verify_token(token)
            if payload.get("type") != "access":
                return JSONResponse(status_code=401, content={"detail": "请使用 access token"})
        except HTTPException as e:
            return JSONResponse(status_code=e.status_code, content={"detail": e.detail})

        user_id = int(payload["sub"])
        request.state.user_id = user_id
        request.state.username = payload["username"]
        request.state.user_permissions = get_user_permissions(user_id)

        # RBAC 检查：匹配路由权限表
        required_perm = self._match_permission(method, path)
        if required_perm and required_perm not in request.state.user_permissions:
            return JSONResponse(status_code=403, content={"detail": f"需要权限: {required_perm}"})

        return await call_next(request)

    @staticmethod
    def _match_permission(method: str, path: str) -> str | None:
        """简单路径匹配：优先精确匹配，再前缀匹配。"""
        # 先精确匹配
        key = (method, path)
        if key in ROUTE_PERMISSIONS:
            return ROUTE_PERMISSIONS[key]

        # 再前缀匹配（处理 /api/users/{id} 这种路径参数）
        path_parts = path.rstrip("/").split("/")
        for (m, pattern), perm in ROUTE_PERMISSIONS.items():
            if m != method:
                continue
            pattern_parts = pattern.rstrip("/").split("/")
            if len(path_parts) != len(pattern_parts):
                continue
            match = True
            for pp, pt in zip(path_parts, pattern_parts):
                if pt.startswith("{") and pt.endswith("}"):
                    continue  # 路径参数，跳过
                if pp != pt:
                    match = False
                    break
            if match:
                return perm
        return None
```

- [ ] **Step 2: Verify auth.py has no syntax errors**

Run: `python -c "import ast; ast.parse(open('auth.py').read()); print('OK')"`

Expected: `OK`

---

### Task 3: Modify server.py

**Files:**
- Modify: `server.py`

- [ ] **Step 1: Update imports and lifespan to include auth init**

Replace the import section (lines 12-25) with:

```python
import asyncio
import sqlite3
import os
import csv
import io
from datetime import datetime
from contextlib import asynccontextmanager

import requests
import pandas as pd
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

# ============================================================
# OneNet IoT 平台配置 — 在 config.py 中修改
# ============================================================
from config import PRODUCT_ID, DEVICE_NAME, TOKEN, HOST, PORT, REFRESH_RATE, ALARM_THRESHOLD

API_URL = "https://iot-api.heclouds.com/thingmodel/query-device-property"

# ============================================================
# 认证模块
# ============================================================
from auth import init_auth_db, auth_router, admin_router, AuthMiddleware, verify_token, get_user_permissions
```

- [ ] **Step 2: Update lifespan to call init_auth_db**

Replace the lifespan function (lines 219-222) with:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    init_auth_db()
    yield
```

- [ ] **Step 3: Add auth routers and middleware, update StaticFiles**

After the lifespan block, replace the `app = FastAPI(...)` line and the StaticFiles mount with:

```python
app = FastAPI(title="Saturation Monitor", lifespan=lifespan)

# 注册认证路由
app.include_router(auth_router)
app.include_router(admin_router)

# 注册鉴权中间件
app.add_middleware(AuthMiddleware)

# ============================================================
# REST API 端点（现有）
# ============================================================

@app.get("/api/saturation/current")
def api_current():
    # ... (keep existing code unchanged)
```

Then at the bottom of the file, replace:

```python
app.mount("/", StaticFiles(directory=os.path.join(BASE_DIR, "static"), html=True), name="static")
```

with:

```python
# 静态文件托管（不含 html=True，由下面的 / 路由控制入口）
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")

# 根路径 → 登录页（首次访问即显示登录页）
from fastapi.responses import FileResponse

@app.get("/")
def root():
    return FileResponse(os.path.join(BASE_DIR, "static", "login.html"))

@app.get("/index.html")
def dashboard():
    return FileResponse(os.path.join(BASE_DIR, "static", "index.html"))
```

- [ ] **Step 4: Update WebSocket endpoint to require token**

Replace the WebSocket function signature and first lines (lines 318-339) with:

```python
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket 端点 — 需通过 ?token=xxx 传递 JWT 鉴权。

    连接: ws://localhost:8000/ws?token=<access_token>
    """
    token = ws.query_params.get("token") if hasattr(ws, "query_params") else None
    if not token:
        await ws.close(code=4001, reason="缺少认证 token")
        return

    try:
        payload = verify_token(token)
    except Exception:
        await ws.close(code=4001, reason="token 无效或已过期")
        return

    await ws.accept()
    # ... (rest of existing code unchanged)
```

- [ ] **Step 5: Verify server.py has no syntax errors**

Run: `python -c "import ast; ast.parse(open('server.py').read()); print('OK')"`

Expected: `OK`

---

### Task 4: Create login.html

**Files:**
- Create: `static/login.html`

- [ ] **Step 1: Write login.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>登录 — 电缆桥架饱和度监控</title>
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <link rel="stylesheet" href="/static/css/style.css">
</head>
<body class="login-body">
    <canvas id="particles-canvas"></canvas>

    <div class="login-wrapper">
        <div class="login-card">
            <!-- 左侧品牌区 -->
            <div class="login-brand">
                <div class="login-logo">⚡</div>
                <div class="login-title">电缆桥架<br>饱和度监控平台</div>
                <div class="login-divider"></div>
                <p class="login-desc">
                    实时监控 · 智能报警<br>
                    OneNet 物联网云平台<br>
                    企业级 RBAC 安全管控
                </p>
                <div class="login-version">v2.0 Enterprise</div>
            </div>

            <!-- 右侧表单区 -->
            <div class="login-form">
                <h2 class="login-heading">🔐 用户登录</h2>
                <p class="login-subtitle">选择认证方式以继续</p>

                <!-- 认证方式标签 -->
                <div class="login-tabs">
                    <button class="login-tab active" data-tab="local" onclick="switchTab('local')">本地账号</button>
                    <button class="login-tab" data-tab="ldap" onclick="switchTab('ldap')">LDAP / AD</button>
                </div>

                <!-- 错误提示 -->
                <div id="login-error" class="login-error hidden"></div>

                <!-- 表单 -->
                <div class="login-field">
                    <label class="login-label">用户名</label>
                    <input type="text" id="login-username" class="login-input" placeholder="admin" autocomplete="username" autofocus>
                </div>
                <div class="login-field">
                    <label class="login-label">密码</label>
                    <input type="password" id="login-password" class="login-input" placeholder="••••••••" autocomplete="current-password">
                </div>

                <button id="login-btn" class="login-btn" onclick="doLogin()">➜ 登 录</button>

                <div class="login-footer-text">首次登录请使用默认账号 admin / admin123</div>
            </div>
        </div>
    </div>

    <script src="/static/js/particles.js"></script>
    <script>
        // 粒子背景
        Particles.init('particles-canvas');

        let authType = 'local';

        function switchTab(type) {
            authType = type;
            document.querySelectorAll('.login-tab').forEach(t => t.classList.toggle('active', t.dataset.tab === type));
            const input = document.getElementById('login-username');
            input.placeholder = type === 'ldap' ? '域账号' : 'admin';
        }

        function showError(msg) {
            const el = document.getElementById('login-error');
            el.textContent = msg;
            el.classList.remove('hidden');
        }

        function hideError() {
            document.getElementById('login-error').classList.add('hidden');
        }

        async function doLogin() {
            hideError();
            const username = document.getElementById('login-username').value.trim();
            const password = document.getElementById('login-password').value;

            if (!username || !password) {
                showError('请输入用户名和密码');
                return;
            }

            const btn = document.getElementById('login-btn');
            btn.textContent = '登录中...';
            btn.disabled = true;

            try {
                const resp = await fetch('/api/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ username, password, auth_type: authType }),
                });

                const data = await resp.json();

                if (!resp.ok) {
                    showError(data.detail || '登录失败');
                    btn.textContent = '➜ 登 录';
                    btn.disabled = false;
                    return;
                }

                // 存储 token
                localStorage.setItem('access_token', data.access_token);
                localStorage.setItem('refresh_token', data.refresh_token);
                localStorage.setItem('user_info', JSON.stringify(data.user));

                // 跳转仪表板
                window.location.replace('/index.html');
            } catch (e) {
                showError('网络错误，请检查服务器连接');
                btn.textContent = '➜ 登 录';
                btn.disabled = false;
            }
        }

        // 回车键登录
        document.getElementById('login-password').addEventListener('keydown', function(e) {
            if (e.key === 'Enter') doLogin();
        });
        document.getElementById('login-username').addEventListener('keydown', function(e) {
            if (e.key === 'Enter') doLogin();
        });
    </script>
</body>
</html>
```

---

### Task 5: Create auth.js

**Files:**
- Create: `static/js/auth.js`

- [ ] **Step 1: Write auth.js**

```js
/**
 * 认证工具模块 — token 管理、自动刷新、401 拦截
 */
const Auth = {
  getToken() {
    return localStorage.getItem('access_token');
  },

  getRefreshToken() {
    return localStorage.getItem('refresh_token');
  },

  setTokens(access, refresh) {
    localStorage.setItem('access_token', access);
    if (refresh) localStorage.setItem('refresh_token', refresh);
  },

  getUser() {
    try {
      return JSON.parse(localStorage.getItem('user_info'));
    } catch (e) { return null; }
  },

  getAuthHeaders() {
    const token = this.getToken();
    return token ? { 'Authorization': 'Bearer ' + token } : {};
  },

  async refreshAccessToken() {
    const refresh = this.getRefreshToken();
    if (!refresh) return false;
    try {
      const resp = await fetch('/api/auth/refresh', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: refresh }),
      });
      if (resp.ok) {
        const data = await resp.json();
        localStorage.setItem('access_token', data.access_token);
        return true;
      }
    } catch (e) { /* ignore */ }
    return false;
  },

  logout() {
    localStorage.removeItem('access_token');
    localStorage.removeItem('refresh_token');
    localStorage.removeItem('user_info');
    window.location.replace('/login.html');
  },

  /**
   * 封装 fetch，自动附带 token + 401 自动刷新。
   * 用法同 fetch，额外返回 resp（不自动 parse body）。
   */
  async fetchWithAuth(url, options = {}) {
    options.headers = { ...(options.headers || {}), ...this.getAuthHeaders() };
    let resp = await fetch(url, options);

    if (resp.status === 401) {
      // token 过期，尝试刷新
      const refreshed = await this.refreshAccessToken();
      if (refreshed) {
        options.headers = { ...(options.headers || {}), ...this.getAuthHeaders() };
        resp = await fetch(url, options);
      } else {
        this.logout();
        throw new Error('认证已过期');
      }
    }
    return resp;
  },

  /**
   * 检查登录状态，无 token 则跳转登录页。
   * 仪表板页面加载时调用。
   */
  guard() {
    if (!this.getToken()) {
      window.location.replace('/login.html');
      return false;
    }
    return true;
  },

  /**
   * 检查用户是否拥有某项权限
   */
  hasPermission(code) {
    const user = this.getUser();
    return user && user.permissions && user.permissions.includes(code);
  },
};
```

---

### Task 6: Create admin.js

**Files:**
- Create: `static/js/admin.js`

- [ ] **Step 1: Write admin.js**

```js
/**
 * 管理面板 — 用户管理 + 角色管理
 */
(function () {
  'use strict';

  const $ = (sel) => document.querySelector(sel);

  let rolesData = [];
  let allPermissions = [];

  // 打开管理面板
  function open() {
    $('#admin-panel').classList.remove('hidden');
    switchAdminTab('users');
  }

  // 关闭管理面板
  function close() {
    $('#admin-panel').classList.add('hidden');
  }

  // 切换标签页
  function switchAdminTab(tab) {
    document.querySelectorAll('.admin-tab').forEach(el => {
      el.classList.toggle('active', el.dataset.tab === tab);
    });
    $('#admin-users-tab').style.display = tab === 'users' ? 'block' : 'none';
    $('#admin-roles-tab').style.display = tab === 'roles' ? 'block' : 'none';
    if (tab === 'users') loadUsers();
    if (tab === 'roles') loadRoles();
  }

  // ========== 用户管理 ==========
  async function loadUsers() {
    try {
      const resp = await Auth.fetchWithAuth('/api/users');
      const users = await resp.json();
      renderUserTable(users);
    } catch (e) { console.error('加载用户列表失败', e); }
  }

  function renderUserTable(users) {
    const tbody = $('#users-table-body');
    tbody.innerHTML = users.map(u => `
      <tr>
        <td><code>${esc(u.username)}</code></td>
        <td>${esc(u.display_name)}</td>
        <td><span class="user-tag tag-${u.auth_type}">${u.auth_type === 'ldap' ? 'LDAP' : '本地'}</span></td>
        <td>${esc(u.role_names.join(', '))}</td>
        <td><span class="status-dot ${u.is_active ? 'on' : 'off'}">●</span> ${u.is_active ? '启用' : '禁用'}</td>
        <td>
          <button class="btn-glass btn-sm" onclick="Admin.editUser(${u.id})">编辑</button>
          <button class="btn-glass btn-sm btn-danger" onclick="Admin.deleteUser(${u.id}, '${esc(u.username)}')">删除</button>
        </td>
      </tr>
    `).join('');
  }

  async function editUser(id) {
    // 获取用户详情 + 所有角色
    try {
      const [usersResp, rolesResp] = await Promise.all([
        Auth.fetchWithAuth('/api/users'),
        Auth.fetchWithAuth('/api/roles'),
      ]);
      const users = await usersResp.json();
      const roles = await rolesResp.json();
      const user = users.find(u => u.id === id);
      if (!user) return;
      showUserModal(user, roles);
    } catch (e) { console.error(e); }
  }

  async function deleteUser(id, username) {
    if (!confirm(`确定删除用户 "${username}" 吗？此操作不可恢复。`)) return;
    try {
      const resp = await Auth.fetchWithAuth('/api/users/' + id, { method: 'DELETE' });
      if (resp.ok) loadUsers();
      else alert('删除失败');
    } catch (e) { console.error(e); }
  }

  function showUserModal(user, roles) {
    const isNew = !user;
    const u = user || { username: '', display_name: '', auth_type: 'local', is_active: true, role_ids: [] };

    const roleChecks = roles.map(r => `
      <label class="admin-check-label">
        <input type="checkbox" value="${r.id}" ${u.role_ids.includes(r.id) ? 'checked' : ''}> ${esc(r.name)}
      </label>
    `).join('');

    const html = `
      <div class="admin-modal-content">
        <h3>${isNew ? '新建用户' : '编辑用户'}</h3>
        <div class="admin-field">
          <label>用户名</label>
          <input type="text" id="mu-username" class="login-input" value="${esc(u.username)}" ${!isNew ? 'disabled' : ''}>
        </div>
        <div class="admin-field">
          <label>显示名称</label>
          <input type="text" id="mu-display" class="login-input" value="${esc(u.display_name)}">
        </div>
        <div class="admin-field">
          <label>认证方式</label>
          <select id="mu-auth-type" class="login-input">
            <option value="local" ${u.auth_type === 'local' ? 'selected' : ''}>本地账号</option>
            <option value="ldap" ${u.auth_type === 'ldap' ? 'selected' : ''}>LDAP / AD</option>
          </select>
        </div>
        <div class="admin-field" id="mu-pw-field" style="display:${isNew && u.auth_type === 'local' ? 'block' : 'none'}">
          <label>${isNew ? '密码' : '新密码（留空不修改）'}</label>
          <input type="password" id="mu-password" class="login-input" placeholder="${isNew ? '' : '留空不修改'}">
        </div>
        <div class="admin-field">
          <label><input type="checkbox" id="mu-active" ${u.is_active ? 'checked' : ''}> 启用账号</label>
        </div>
        <div class="admin-field">
          <label>角色</label>
          <div class="admin-check-group">${roleChecks}</div>
        </div>
        <div class="admin-modal-actions">
          <button class="btn-glass" onclick="Admin.saveUser(${isNew ? 0 : u.id})">保存</button>
          <button class="btn-glass" onclick="Admin.closeModal()">取消</button>
        </div>
      </div>`;
    showModal(html);

    document.getElementById('mu-auth-type').addEventListener('change', function () {
      const pwField = document.getElementById('mu-pw-field');
      pwField.style.display = this.value === 'ldap' ? 'none' : 'block';
    });
  }

  async function saveUser(id) {
    const username = $('#mu-username').value.trim();
    const display_name = $('#mu-display').value.trim();
    const auth_type = $('#mu-auth-type').value;
    const is_active = $('#mu-active').checked;
    const password = $('#mu-password') ? $('#mu-password').value : '';
    const role_ids = Array.from(document.querySelectorAll('#admin-modal .admin-check-label input:checked'))
      .map(cb => parseInt(cb.value));

    const body = { username, display_name, auth_type, is_active, role_ids };
    if (password) body.password = password;

    try {
      const url = id ? '/api/users/' + id : '/api/users';
      const method = id ? 'PUT' : 'POST';
      const resp = await Auth.fetchWithAuth(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
      if (resp.ok) { closeModal(); loadUsers(); }
      else { const err = await resp.json(); alert(err.detail || '保存失败'); }
    } catch (e) { console.error(e); }
  }

  // ========== 角色管理 ==========
  async function loadRoles() {
    try {
      const [rolesResp, permsResp] = await Promise.all([
        Auth.fetchWithAuth('/api/roles'),
        Auth.fetchWithAuth('/api/permissions'),
      ]);
      rolesData = await rolesResp.json();
      allPermissions = await permsResp.json();
      renderRoleList();
    } catch (e) { console.error(e); }
  }

  function renderRoleList() {
    const selectedId = $('#admin-roles-tab').dataset.selectedRoleId;
    const container = $('#roles-list');
    container.innerHTML = rolesData.map(r => `
      <div class="role-item ${r.id == selectedId ? 'selected' : ''}" onclick="Admin.selectRole(${r.id})">
        ${r.is_system ? '🔒' : '○'} ${esc(r.name)}
      </div>
    `).join('') + `<button class="btn-glass btn-sm" style="margin-top:8px" onclick="Admin.createRole()">+ 新建角色</button>`;

    if (selectedId) {
      const role = rolesData.find(r => r.id == selectedId);
      if (role) renderRolePerms(role);
    }
  }

  function renderRolePerms(role) {
    const permIds = new Set(role.permissions.map(p => p.id));
    const permsHtml = allPermissions.map(p => `
      <label class="admin-check-label">
        <input type="checkbox" value="${p.id}" ${permIds.has(p.id) ? 'checked' : ''}> ${esc(p.name)}
        <small>(${esc(p.code)})</small>
      </label>
    `).join('');

    const isSystem = role.is_system;
    $('#role-perms').innerHTML = `
      <div class="admin-field">
        <label>角色名</label>
        <input type="text" id="mr-name" class="login-input" value="${esc(role.name)}" ${isSystem ? 'disabled' : ''}>
      </div>
      <div class="admin-field">
        <label>描述</label>
        <input type="text" id="mr-desc" class="login-input" value="${esc(role.description || '')}">
      </div>
      <div class="admin-field">
        <label>权限</label>
        <div class="admin-check-group">${permsHtml}</div>
      </div>
      <div class="admin-modal-actions">
        <button class="btn-glass" onclick="Admin.saveRole(${role.id})">保存</button>
        ${!isSystem ? `<button class="btn-glass btn-danger" onclick="Admin.deleteRole(${role.id}, '${esc(role.name)}')">删除</button>` : ''}
      </div>`;
  }

  function selectRole(id) {
    $('#admin-roles-tab').dataset.selectedRoleId = id;
    renderRoleList();
  }

  function createRole() {
    $('#admin-roles-tab').dataset.selectedRoleId = '';
    renderRoleList();
    $('#role-perms').innerHTML = `
      <div class="admin-field">
        <label>角色名</label>
        <input type="text" id="mr-name" class="login-input" placeholder="新角色名称">
      </div>
      <div class="admin-field">
        <label>描述</label>
        <input type="text" id="mr-desc" class="login-input" placeholder="角色说明">
      </div>
      <div class="admin-field">
        <label>权限</label>
        <div class="admin-check-group">
          ${allPermissions.map(p => `
            <label class="admin-check-label">
              <input type="checkbox" value="${p.id}"> ${esc(p.name)} <small>(${esc(p.code)})</small>
            </label>
          `).join('')}
        </div>
      </div>
      <div class="admin-modal-actions">
        <button class="btn-glass" onclick="Admin.saveRole(0)">创建</button>
      </div>`;
  }

  async function saveRole(id) {
    const name = $('#mr-name').value.trim();
    const description = $('#mr-desc').value.trim();
    const permission_ids = Array.from(document.querySelectorAll('#role-perms .admin-check-label input:checked'))
      .map(cb => parseInt(cb.value));

    if (!name) { alert('角色名不能为空'); return; }

    try {
      const url = id ? '/api/roles/' + id : '/api/roles';
      const method = id ? 'PUT' : 'POST';
      const resp = await Auth.fetchWithAuth(url, { method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name, description, permission_ids }) });
      if (resp.ok) {
        if (!id) $('#admin-roles-tab').dataset.selectedRoleId = '';
        loadRoles();
      } else { const err = await resp.json(); alert(err.detail || '保存失败'); }
    } catch (e) { console.error(e); }
  }

  async function deleteRole(id, name) {
    if (!confirm(`确定删除角色 "${name}" 吗？`)) return;
    try {
      const resp = await Auth.fetchWithAuth('/api/roles/' + id, { method: 'DELETE' });
      if (resp.ok) { $('#admin-roles-tab').dataset.selectedRoleId = ''; loadRoles(); }
      else { const err = await resp.json(); alert(err.detail || '删除失败'); }
    } catch (e) { console.error(e); }
  }

  // ========== 模态框 ==========
  function showModal(innerHtml) {
    $('#admin-modal').innerHTML = innerHtml;
    $('#admin-modal').classList.remove('hidden');
  }

  function closeModal() {
    $('#admin-modal').classList.add('hidden');
  }

  // ========== 工具 ==========
  function esc(s) {
    if (!s) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // 导出
  window.Admin = { open, close, switchAdminTab, editUser, deleteUser, saveUser,
    selectRole, createRole, saveRole, deleteRole, closeModal };
})();
```

---

### Task 7: Modify index.html (dashboard)

**Files:**
- Modify: `static/index.html`

- [ ] **Step 1: Add token guard script at the very top of `<body>`**

Insert immediately after `<body>`:

```html
<!-- 登录守卫：无 token 则跳转登录页 -->
<script src="/static/js/auth.js"></script>
<script>Auth.guard();</script>
```

- [ ] **Step 2: Add "管理" button in header-right**

Replace the header-right div (around line 23-26) with:

```html
<div class="header-right">
    <button class="btn-glass" id="btn-admin" style="display:none" onclick="Admin.open()">🔑 管理</button>
    <span class="header-info" id="clock">--:--:--</span>
    <span id="ws-badge" class="badge badge-warn">⬡ 连接中...</span>
    <button class="btn-glass" onclick="Auth.logout()" title="退出登录">↪</button>
</div>
```

- [ ] **Step 3: Add admin panel and modal HTML before `</body>`**

Insert before the closing `</body>` tag (after the settings overlay div):

```html
<!-- 管理面板 -->
<div id="admin-panel" class="overlay hidden">
    <div class="glass-card admin-dialog">
        <div class="admin-tabs-bar">
            <button class="admin-tab active" data-tab="users" onclick="Admin.switchAdminTab('users')">📋 用户管理</button>
            <button class="admin-tab" data-tab="roles" onclick="Admin.switchAdminTab('roles')">🔑 角色管理</button>
            <span style="flex:1"></span>
            <button class="btn-glass" onclick="Admin.close()">✕</button>
        </div>
        <div id="admin-users-tab">
            <div style="margin-bottom:12px">
                <button class="btn-glass" onclick="Admin.editUser(0)">+ 新建用户</button>
            </div>
            <table class="admin-table">
                <thead><tr>
                    <th>用户名</th><th>显示名</th><th>认证</th><th>角色</th><th>状态</th><th>操作</th>
                </tr></thead>
                <tbody id="users-table-body"></tbody>
            </table>
        </div>
        <div id="admin-roles-tab" style="display:none" data-selected-role-id="">
            <div style="display:flex;gap:16px">
                <div id="roles-list" style="flex:0 0 180px;border-right:1px solid rgba(30,60,100,0.3);padding-right:12px"></div>
                <div id="role-perms" style="flex:1"></div>
            </div>
        </div>
    </div>
</div>

<div id="admin-modal" class="overlay hidden"></div>
```

- [ ] **Step 4: Add admin.js script tag**

Add before `</body>` alongside other scripts:

```html
<script src="/static/js/admin.js"></script>
```

---

### Task 8: Modify app.js

**Files:**
- Modify: `static/js/app.js`

- [ ] **Step 1: Add admin button visibility based on permissions**

In the `init()` function (line 239), add at the beginning:

```js
// 显示管理按钮（如果用户有管理权限）
if (Auth.hasPermission('users:manage') || Auth.hasPermission('roles:manage')) {
  const btnAdmin = $('#btn-admin');
  if (btnAdmin) btnAdmin.style.display = '';
}
```

- [ ] **Step 2: Update WebSocket connection to pass token**

In `connectWebSocket()` (line 143), change the wsUrl construction to:

```js
const token = Auth.getToken();
const wsUrl = `${protocol}//${window.location.host}/ws${token ? '?token=' + encodeURIComponent(token) : ''}`;
```

---

### Task 9: Modify style.css

**Files:**
- Modify: `static/css/style.css`

- [ ] **Step 1: Append login and admin styles**

Append the following CSS at the end of `static/css/style.css`:

```css
/* ===== 登录页面 ===== */
.login-body {
    display: flex;
    align-items: center;
    justify-content: center;
    min-height: 100vh;
    overflow: hidden;
}
.login-wrapper {
    position: relative; z-index: 1;
    display: flex;
    align-items: center;
    justify-content: center;
    width: 100%;
    padding: 20px;
}
.login-card {
    display: flex;
    width: 780px;
    height: 440px;
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid rgba(30,60,100,0.5);
    box-shadow: 0 0 60px rgba(0,229,255,0.08);
    background: #0c1a30;
}
.login-brand {
    flex: 0 0 45%;
    background: linear-gradient(160deg, #070e1a 0%, #0c1f3a 100%);
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    padding: 40px;
    border-right: 1px solid rgba(30,60,100,0.3);
}
.login-logo { font-size: 56px; margin-bottom: 16px; }
.login-title {
    font-family: 'Orbitron', monospace;
    font-size: 20px;
    font-weight: 700;
    color: #00e5ff;
    text-align: center;
    line-height: 1.5;
}
.login-divider {
    width: 48px;
    height: 2px;
    background: #00e5ff;
    margin: 18px 0;
    opacity: 0.4;
}
.login-desc {
    color: #5a7a9a;
    font-size: 13px;
    text-align: center;
    line-height: 2.0;
}
.login-version {
    margin-top: 20px;
    font-size: 11px;
    color: #3a5a7a;
}
.login-form {
    flex: 1;
    background: linear-gradient(180deg, #0c1a30 0%, #081020 100%);
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 48px 44px;
}
.login-heading {
    font-size: 22px;
    color: #e0e8f0;
    margin-bottom: 4px;
}
.login-subtitle {
    color: #5a7a9a;
    font-size: 13px;
    margin-bottom: 28px;
}
.login-tabs {
    display: flex;
    margin-bottom: 24px;
    border-radius: 6px;
    overflow: hidden;
    border: 1px solid rgba(30,60,100,0.5);
}
.login-tab {
    flex: 1;
    text-align: center;
    padding: 9px 0;
    background: transparent;
    color: #5a7a9a;
    font-size: 13px;
    font-weight: 600;
    cursor: pointer;
    border: none;
    transition: all 0.2s;
}
.login-tab.active {
    background: rgba(0,229,255,0.1);
    color: #00e5ff;
}
.login-error {
    background: rgba(255,51,51,0.1);
    border: 1px solid rgba(255,51,51,0.3);
    color: #ff3333;
    padding: 8px 12px;
    border-radius: 6px;
    font-size: 13px;
    margin-bottom: 16px;
}
.login-error.hidden { display: none; }
.login-field { margin-bottom: 16px; }
.login-label {
    display: block;
    color: #5a7a9a;
    font-size: 12px;
    font-weight: 600;
    margin-bottom: 5px;
}
.login-input {
    width: 100%;
    background: rgba(10,25,50,0.6);
    border: 1px solid rgba(30,60,100,0.4);
    border-radius: 6px;
    padding: 10px 14px;
    color: #e0e8f0;
    font-size: 14px;
    outline: none;
    transition: border-color 0.2s;
    box-sizing: border-box;
}
.login-input:focus { border-color: #00e5ff; }
.login-btn {
    width: 100%;
    padding: 12px;
    border-radius: 6px;
    border: none;
    background: linear-gradient(135deg, #00b8d4, #00e5ff);
    color: #060b14;
    font-size: 15px;
    font-weight: 700;
    cursor: pointer;
    margin-bottom: 18px;
    box-shadow: 0 0 24px rgba(0,229,255,0.25);
    transition: opacity 0.2s;
}
.login-btn:hover { opacity: 0.9; }
.login-btn:disabled { opacity: 0.5; cursor: default; }
.login-footer-text {
    text-align: center;
    font-size: 11px;
    color: #3a5a7a;
}

/* ===== 管理面板 ===== */
.admin-dialog {
    width: 90vw;
    max-width: 900px;
    max-height: 80vh;
    overflow-y: auto;
    padding: 20px;
}
.admin-tabs-bar {
    display: flex;
    gap: 0;
    margin-bottom: 16px;
    border-bottom: 1px solid rgba(30,60,100,0.3);
    padding-bottom: 0;
    align-items: center;
}
.admin-tab {
    padding: 8px 16px;
    background: none;
    border: none;
    border-bottom: 2px solid transparent;
    color: #5a7a9a;
    font-size: 14px;
    cursor: pointer;
    font-family: inherit;
    transition: all 0.2s;
}
.admin-tab.active {
    color: #00e5ff;
    border-bottom-color: #00e5ff;
}
.admin-tab:hover { color: #e0e8f0; }
.admin-table {
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
}
.admin-table th {
    color: #5a7a9a;
    text-align: left;
    padding: 8px;
    border-bottom: 1px solid rgba(30,60,100,0.3);
    font-weight: 600;
}
.admin-table td {
    padding: 8px;
    border-bottom: 1px solid rgba(30,60,100,0.1);
}
.admin-table code {
    font-family: 'JetBrains Mono', monospace;
    background: rgba(0,229,255,0.05);
    padding: 1px 6px;
    border-radius: 3px;
    font-size: 12px;
}
.user-tag {
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 600;
}
.user-tag.tag-local { background: rgba(0,229,255,0.1); color: #00e5ff; }
.user-tag.tag-ldap  { background: rgba(255,170,0,0.1); color: #ffaa00; }
.status-dot { font-size: 10px; }
.status-dot.on { color: #00ff88; }
.status-dot.off { color: #ff3333; }
.btn-sm { font-size: 12px; padding: 3px 10px; }
.btn-danger { border-color: rgba(255,51,51,0.3); color: #ff3333; }
.btn-danger:hover { background: rgba(255,51,51,0.15); }
.role-item {
    padding: 6px 8px;
    border-radius: 4px;
    font-size: 13px;
    cursor: pointer;
    color: #e0e8f0;
    margin-bottom: 2px;
}
.role-item:hover { background: rgba(0,229,255,0.05); }
.role-item.selected { background: rgba(0,229,255,0.08); color: #00e5ff; }

/* ===== 管理模态框 ===== */
#admin-modal {
    z-index: 1001;
}
#admin-modal.hidden { display: none; }
#admin-modal:not(.hidden) { display: flex; }
.admin-modal-content {
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 12px;
    padding: 24px;
    width: 480px;
    max-height: 80vh;
    overflow-y: auto;
    backdrop-filter: blur(8px);
}
.admin-modal-content h3 {
    font-size: 18px;
    color: var(--text-primary);
    margin-bottom: 16px;
}
.admin-field {
    margin-bottom: 12px;
}
.admin-field label {
    display: block;
    color: #5a7a9a;
    font-size: 13px;
    margin-bottom: 4px;
}
.admin-check-group {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
    margin-top: 4px;
}
.admin-check-label {
    display: flex !important;
    align-items: center;
    gap: 4px;
    font-size: 13px !important;
    color: #e0e8f0;
    cursor: pointer;
}
.admin-check-label small { color: #5a7a9a; font-size: 11px; }
.admin-check-label input[type="checkbox"] { accent-color: var(--cyan); }
.admin-modal-actions {
    display: flex;
    gap: 10px;
    margin-top: 20px;
    justify-content: flex-end;
}

/* ===== 响应式: 登录页小屏适配 ===== */
@media (max-width: 800px) {
    .login-card {
        flex-direction: column;
        width: 100%;
        height: auto;
    }
    .login-brand {
        flex: none;
        padding: 24px;
        border-right: none;
        border-bottom: 1px solid rgba(30,60,100,0.3);
    }
    .login-form {
        padding: 32px 24px;
    }
}
```

---

### Task 10: Verify

**Files:**
- All of the above.

- [ ] **Step 1: Check syntax of all Python files**

Run: `python -c "import ast; [ast.parse(open(f).read()) for f in ['server.py', 'auth.py', 'config.py']]; print('All OK')"`

Expected: `All OK`

- [ ] **Step 2: Start server and test login**

Run: `python server.py`
Then visit `http://localhost:8000` in browser.

Expected:
1. `http://localhost:8000` → 直接显示登录页
2. Login with `admin` / `admin123` → redirects to `/index.html`（仪表板）
3. Dashboard shows data as before
4. "管理" button visible for admin user
5. Click "管理" → user/role management panel
6. 直接访问 `/index.html` 无 token → 跳转回登录页

- [ ] **Step 3: Test API endpoints**

```bash
# Login and get token
curl -s -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin123","auth_type":"local"}' | python -m json.tool

# Use token to call protected endpoint
export TOKEN="<access_token from above>"
curl -s http://localhost:8000/api/users -H "Authorization: Bearer $TOKEN" | python -m json.tool

# Test without token (should 401)
curl -s http://localhost:8000/api/saturation/current
```

Expected:
- Login returns `access_token`, `refresh_token`, `user` with permissions
- `/api/users` returns user list
- Unauthenticated request returns 401
```

Expected: all verifications pass.

---

### Task 11: Clean up old database (if needed)

**Files:**
- `data/saturation.db`

- [ ] **Step 1: Delete old DB to trigger fresh init with auth tables**

Run: `rm E:/test/project/project_6_1/data/saturation.db`
(Or keep it if you want to preserve existing monitoring data — auth tables are created alongside existing tables without conflict.)

If keeping old data: just restart server, `init_auth_db()` will add the new tables without touching existing data.

---

## Summary

| # | Task | Files | Time (est) |
|---|------|-------|-----------|
| 1 | Config & deps | config.py, requirements.txt | 2 min |
| 2 | auth.py (backend) | auth.py (new) | 5 min |
| 3 | Modify server.py | server.py | 5 min |
| 4 | login.html | login.html (new) | 3 min |
| 5 | auth.js | auth.js (new) | 2 min |
| 6 | admin.js | admin.js (new) | 5 min |
| 7 | Modify index.html | index.html | 3 min |
| 8 | Modify app.js | app.js | 2 min |
| 9 | Modify style.css | style.css | 2 min |
| 10 | Verify | all | 5 min |
| 11 | DB cleanup | saturation.db | 1 min |

**Total: ~35 min**
