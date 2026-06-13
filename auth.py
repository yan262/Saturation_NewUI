"""
认证与 RBAC 权限管理模块
========================
本模块是整个登录认证系统的核心，提供以下功能：

  1. 数据库初始化 — 自动建表 + 预置权限/角色 + 默认管理员账号
  2. 密码工具 — bcrypt 哈希和验证
  3. JWT 工具 — access token（短期）+ refresh token（长期）签发与验证
  4. LDAP/AD 认证 — 可选的企业域控登录
  5. RBAC 权限 — 用户 → 角色 → 权限，三层模型
  6. Auth 路由 — 登录、刷新 token、获取当前用户、修改密码
  7. Admin 路由 — 用户 CRUD、角色 CRUD、权限列表
  8. AuthMiddleware — ASGI 中间件，拦截所有 /api/* 请求进行 JWT 鉴权 + 权限检查

调用链:
  浏览器 → AuthMiddleware（鉴权） → 路由函数 → 数据库
                ↑
           server.py 启动时挂载
"""

import logging
from datetime import datetime, timedelta

import jwt   # PyJWT — 签发和验证 JWT token
import bcrypt   # bcrypt — 密码哈希（比 SHA 更安全，自带 salt）
from fastapi import APIRouter, Request, HTTPException, Depends
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

logger = logging.getLogger(__name__)

# ---- 配置（来自 config.py）----
from config import (
    JWT_SECRET,                   # JWT 签名密钥（生产环境必须修改）
    JWT_ALGORITHM,                # 签名算法，默认 HS256
    ACCESS_TOKEN_EXPIRE_MINUTES,  # access token 有效期（分钟），默认 30
    REFRESH_TOKEN_EXPIRE_DAYS,    # refresh token 有效期（天），默认 7
    LDAP_ENABLED,                 # 是否启用 LDAP 认证
    LDAP_SERVER,                  # LDAP 服务器地址
    LDAP_BASE_DN,                 # LDAP 基础 DN
    LDAP_DOMAIN,                  # AD 域名
)

from database import get_db

# ============================================================
# 预置数据 — 系统内置权限和角色，首次启动时自动写入数据库
# ============================================================

# 6 个预置权限（code, 中文名, 说明）
PRESET_PERMISSIONS = [
    ("dashboard:view", "查看仪表板", "查看实时饱和度数据、图表和统计"),
    ("settings:write", "修改监控设置", "修改刷新频率和报警阈值"),
    ("data:export",   "导出 CSV",     "导出全部历史数据为 CSV 文件"),
    ("users:manage",  "用户管理",     "创建、编辑、删除用户"),
    ("roles:manage",  "角色权限管理", "创建角色、分配权限"),
    ("alarms:view",   "查看报警日志", "查看报警历史记录"),
]

# 3 个预置角色（角色名 → 拥有的权限列表）
PRESET_ROLES = {
    "超级管理员": [   # 拥有全部权限
        "dashboard:view", "settings:write", "data:export",
        "users:manage", "roles:manage", "alarms:view",
    ],
    "运维工程师": [   # 可查看仪表板、修改设置、导出数据和查看报警
        "dashboard:view", "settings:write", "data:export", "alarms:view",
    ],
    "只读用户": [   # 只能查看，不能修改任何设置
        "dashboard:view", "alarms:view",
    ],
}

# 路由 → 权限映射表（METHOD, path）→ permission_code
# 中间件根据此表判断每个 API 需要什么权限
ROUTE_PERMISSIONS = {
    # ---- 监控数据 API ----
    ("GET",  "/api/saturation/current"):  "dashboard:view",
    ("GET",  "/api/saturation/history"):  "dashboard:view",
    ("GET",  "/api/saturation/stats"):    "dashboard:view",
    ("GET",  "/api/alarm/logs"):          "alarms:view",
    ("GET",  "/api/export/csv"):          "data:export",
    ("PUT",  "/api/settings"):            "settings:write",
    ("GET",  "/api/settings"):            "dashboard:view",
    # ---- 用户管理 API ----
    ("GET",    "/api/users"):       "users:manage",
    ("POST",   "/api/users"):       "users:manage",
    ("PUT",    "/api/users/{id}"):  "users:manage",
    ("DELETE", "/api/users/{id}"):  "users:manage",
    # ---- 角色管理 API ----
    ("GET",    "/api/roles"):        "roles:manage",
    ("POST",   "/api/roles"):        "roles:manage",
    ("PUT",    "/api/roles/{id}"):   "roles:manage",
    ("DELETE", "/api/roles/{id}"):   "roles:manage",
    ("GET",    "/api/permissions"):  "roles:manage",
}


# ============================================================
# 数据库工具 — 统一使用 database.get_db() 上下文管理器
# ============================================================


def init_auth_db():
    """
    初始化认证相关数据表 + 预置数据 + 默认管理员账号。

    此函数在 server.py 的 lifespan 中调用（应用启动时自动执行）。
    所有表使用 IF NOT EXISTS，反复执行不会报错。
    预置数据使用 INSERT OR IGNORE，不会重复插入。
    """
    with get_db() as conn:
        c = conn.cursor()

        # ---- 5 张核心表 ----

    # 用户表：存储所有可登录的账号
    c.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,        -- 登录名，唯一
        password_hash TEXT,                   -- bcrypt 密码哈希（LDAP 用户可为空）
        display_name TEXT DEFAULT '',         -- 显示名称
        auth_type TEXT DEFAULT 'local',       -- 'local'=本地账号, 'ldap'=域账号
        ldap_dn TEXT,                         -- LDAP 用户的专有名称
        is_active INTEGER DEFAULT 1,          -- 1=启用, 0=禁用
        last_login TEXT,                      -- 最后登录时间
        created_at TEXT NOT NULL              -- 创建时间
    )""")

    # 角色表：预置 3 个 + 管理员可自定义
    c.execute("""CREATE TABLE IF NOT EXISTS roles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,            -- 角色名称，唯一
        description TEXT DEFAULT '',          -- 角色说明
        is_system INTEGER DEFAULT 0,          -- 1=系统预置（不可删除）, 0=自定义
        created_at TEXT NOT NULL
    )""")

    # 权限表：定义所有可用的权限项
    c.execute("""CREATE TABLE IF NOT EXISTS permissions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,            -- 权限码，如 "dashboard:view"
        name TEXT NOT NULL,                   -- 中文名，如 "查看仪表板"
        description TEXT DEFAULT ''           -- 详细说明
    )""")

    # 用户-角色关联表（多对多）
    c.execute("""CREATE TABLE IF NOT EXISTS user_roles (
        user_id INTEGER NOT NULL,
        role_id INTEGER NOT NULL,
        PRIMARY KEY (user_id, role_id),
        FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
        FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE
    )""")

    # 角色-权限关联表（多对多）
    c.execute("""CREATE TABLE IF NOT EXISTS role_permissions (
        role_id INTEGER NOT NULL,
        permission_id INTEGER NOT NULL,
        PRIMARY KEY (role_id, permission_id),
        FOREIGN KEY (role_id) REFERENCES roles(id) ON DELETE CASCADE,
        FOREIGN KEY (permission_id) REFERENCES permissions(id) ON DELETE CASCADE
    )""")

    # ---- 写入预置权限 ----
    for code, name, desc in PRESET_PERMISSIONS:
        c.execute("INSERT OR IGNORE INTO permissions (code, name, description) VALUES (?, ?, ?)",
                  (code, name, desc))

    # 查询所有权限的 code → id 映射，供后续关联使用
    perm_map = {}
    c.execute("SELECT id, code FROM permissions")
    for row in c.fetchall():
        perm_map[row["code"]] = row["id"]

    # ---- 写入预置角色并关联权限 ----
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

    # ---- 默认管理员账号 admin / admin123 ----
    # 仅当 admin 用户不存在时才创建（首次启动）
    c.execute("SELECT id FROM users WHERE username = 'admin'")
    if not c.fetchone():
        # bcrypt.hashpw 自动生成随机 salt，每次结果不同
        pw_hash = bcrypt.hashpw("admin123".encode(), bcrypt.gensalt()).decode()
        c.execute("""INSERT INTO users (username, password_hash, display_name, auth_type, created_at)
                     VALUES ('admin', ?, '管理员', 'local', ?)""", (pw_hash, now))
        # 赋予超级管理员角色
        c.execute("SELECT id FROM users WHERE username = 'admin'")
        uid = c.fetchone()["id"]
        c.execute("SELECT id FROM roles WHERE name = '超级管理员'")
        rid = c.fetchone()["id"]
        c.execute("INSERT INTO user_roles (user_id, role_id) VALUES (?, ?)", (uid, rid))


# ============================================================
# 密码工具 — bcrypt 哈希
# ============================================================

def hash_password(password: str) -> str:
    """对明文密码进行 bcrypt 哈希（自动加盐），返回哈希字符串。"""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    """验证明文密码是否与哈希值匹配。"""
    return bcrypt.checkpw(password.encode(), hashed.encode())


# ============================================================
# JWT 工具 — 签发与验证
# ============================================================

def create_access_token(user_id: int, username: str) -> str:
    """
    签发短期 access token（默认 30 分钟过期）。
    前端将此 token 放在 Authorization: Bearer <token> 请求头中。
    payload 中包含 sub(用户ID)、username、type(固定"access")、exp(过期时间)。
    """
    payload = {
        "sub": str(user_id),
        "username": username,
        "type": "access",
        "exp": datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def create_refresh_token(user_id: int, username: str) -> str:
    """
    签发长期 refresh token（默认 7 天过期）。
    access token 过期后，前端用 refresh token 换取新的 access token。
    不直接用于 API 鉴权，中间件会拒绝 type="refresh" 的 token。
    """
    payload = {
        "sub": str(user_id),
        "username": username,
        "type": "refresh",
        "exp": datetime.utcnow() + timedelta(days=REFRESH_TOKEN_EXPIRE_DAYS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict:
    """
    验证 JWT token 的签名和有效期。
    成功 → 返回 payload 字典
    过期 → 抛出 HTTPException(401, "token 已过期")
    无效 → 抛出 HTTPException(401, "token 无效")
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token 已过期")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="token 无效")


# ============================================================
# LDAP/AD 认证
# ============================================================

def ldap_authenticate(username: str, password: str) -> bool:
    """
    尝试通过 LDAP/AD 服务器验证用户名密码。
    使用简单绑定（Simple Bind）：用 user@domain 格式尝试登录 LDAP 服务器。
    成功 → True，失败/超时/网络不可达 → False。

    注意：LDAP 只验证密码是否正确，用户仍需在本地数据库中存在才能登录。
    """
    if not LDAP_ENABLED:
        return False
    try:
        from ldap3 import Server, Connection, ALL
        server = Server(LDAP_SERVER, get_info=ALL, connect_timeout=5)   # 5 秒连接超时
        user_dn = f"{username}@{LDAP_DOMAIN}"   # AD 格式: user@COMPANY
        conn = Connection(server, user=user_dn, password=password,
                          auto_bind=True, receive_timeout=5)   # 5 秒接收超时
        conn.unbind()
        logger.info("LDAP 认证成功 user=%s", username)
        return True
    except Exception as e:
        logger.warning("LDAP 认证失败 user=%s reason=%s", username, e)
        return False


# ============================================================
# 权限查询
# ============================================================

def get_user_permissions(user_id: int) -> set:
    """
    查询用户拥有的所有权限码。
    通过 user_roles → role_permissions → permissions 三层 JOIN 获取。
    返回集合，如 {"dashboard:view", "alarms:view"}。
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT DISTINCT p.code FROM permissions p
            JOIN role_permissions rp ON p.id = rp.permission_id
            JOIN user_roles ur ON rp.role_id = ur.role_id
            WHERE ur.user_id = ?
        """, (user_id,))
        return {row["code"] for row in c.fetchall()}


def require_permission(code: str):
    """
    FastAPI 依赖注入工厂函数。
    用法: @app.get("/api/users", dependencies=[require_permission("users:manage")])
    在当前请求上下文中检查用户是否拥有指定权限，无权限则自动返回 403。
    """
    def checker(request: Request):
        # 注意：user_permissions 由 AuthMiddleware 在鉴权时设置到 request.state 上
        user_perms = getattr(request.state, "user_permissions", set())
        if code not in user_perms:
            raise HTTPException(status_code=403, detail=f"需要权限: {code}")
    return Depends(checker)


# ============================================================
# 认证路由 — 登录、刷新、个人信息、修改密码
# 这些接口在 AuthMiddleware 的白名单中，不需要鉴权即可访问
# ============================================================

auth_router = APIRouter(prefix="/api/auth", tags=["认证"])


@auth_router.post("/login")
def login(payload: dict):
    """
    用户登录接口（无需鉴权）。
    请求体: {"username": "...", "password": "...", "auth_type": "local|ldap"}

    流程:
      1. 校验用户名和密码非空
      2. 根据 auth_type 选择验证方式：
         - local → 从数据库查用户，bcrypt 验证密码
         - ldap  → 先通过 LDAP 服务器验证密码，再从本地数据库查用户记录
      3. 更新 last_login 时间
      4. 签发 access token + refresh token
      5. 返回 token + 用户基本信息 + 权限列表
    """
    username = payload.get("username", "").strip()
    password = payload.get("password", "")
    auth_type = payload.get("auth_type", "local")

    if not username or not password:
        raise HTTPException(status_code=400, detail="用户名和密码不能为空")

    logger.info("登录尝试 username=%s auth_type=%s", username, auth_type)

    with get_db() as conn:
        c = conn.cursor()
        user = None

        if auth_type == "ldap":
            # LDAP 验证：先通过域控验证密码，再查本地数据库
            if ldap_authenticate(username, password):
                c.execute("SELECT * FROM users WHERE username = ? AND is_active = 1",
                          (username,))
                row = c.fetchone()
                if row:
                    user = dict(row)
            if not user:
                logger.warning("LDAP 密码验证通过但本地无匹配用户 username=%s", username)
                raise HTTPException(status_code=401, detail="用户名或密码错误")
        else:
            # 本地验证：查数据库 → bcrypt 比对密码
            c.execute("SELECT * FROM users WHERE username = ? AND auth_type = 'local' AND is_active = 1",
                      (username,))
            row = c.fetchone()
            if row and verify_password(password, row["password_hash"]):
                user = dict(row)
            else:
                logger.warning("本地登录失败 username=%s", username)
                raise HTTPException(status_code=401, detail="用户名或密码错误")

        # 更新最后登录时间
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("UPDATE users SET last_login = ? WHERE id = ?", (now, user["id"]))

    # 签发双 token
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
    """
    刷新 access token（无需鉴权）。
    请求体: {"refresh_token": "..."}

    用长期有效的 refresh token 换取新的短期 access token。
    不会签发新的 refresh token（refresh token 过期需重新登录）。
    """
    token = payload.get("refresh_token", "")
    if not token:
        raise HTTPException(status_code=400, detail="缺少 refresh_token")

    # 验证 refresh token 的类型和有效性
    try:
        data = verify_token(token)
        if data.get("type") != "refresh":   # 防止用 access token 来刷新
            raise HTTPException(status_code=401, detail="token 类型错误")
    except HTTPException:
        raise HTTPException(status_code=401, detail="refresh_token 无效或已过期")

    user_id = int(data["sub"])
    username = data["username"]

    # 确认用户仍然存在且未被禁用
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE id = ? AND is_active = 1", (user_id,))
        if not c.fetchone():
            raise HTTPException(status_code=403, detail="账号已被禁用")

    return {"access_token": create_access_token(user_id, username)}


@auth_router.get("/me")
def me(request: Request):
    """
    获取当前登录用户的信息（需鉴权）。
    request.state.user_id 由 AuthMiddleware 在鉴权时注入。
    返回用户基本信息 + 权限列表，前端用于判断显示哪些按钮/菜单。
    """
    user_id = int(request.state.user_id)
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id, username, display_name, auth_type, last_login, created_at FROM users WHERE id = ?",
                  (user_id,))
        row = c.fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="用户不存在")
    perms = get_user_permissions(user_id)
    return {**dict(row), "permissions": sorted(perms)}


@auth_router.put("/password")
def change_password(payload: dict, request: Request):
    """
    修改当前用户的密码（需鉴权）。
    请求体: {"old_password": "...", "new_password": "..."}

    仅本地账号支持修改密码，LDAP 用户密码由域控管理。
    """
    old_pw = payload.get("old_password", "")
    new_pw = payload.get("new_password", "")

    if not old_pw:
        raise HTTPException(status_code=400, detail="请输入原密码")
    if not new_pw or len(new_pw) < 8:
        raise HTTPException(status_code=400, detail="新密码至少 8 位")

    user_id = int(request.state.user_id)
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        row = c.fetchone()
        # LDAP 用户不允许在此修改密码
        if not row or row["auth_type"] != "local":
            raise HTTPException(status_code=400, detail="LDAP 账号不支持修改密码")
        # 验证原密码
        if not verify_password(old_pw, row["password_hash"]):
            raise HTTPException(status_code=400, detail="原密码错误")

        c.execute("UPDATE users SET password_hash = ? WHERE id = ?",
                  (hash_password(new_pw), user_id))
    return {"message": "密码修改成功"}


# ============================================================
# 管理路由 — 用户管理（需 users:manage 权限）
# ============================================================

admin_router = APIRouter(prefix="/api", tags=["管理"])


@admin_router.get("/users")
def list_users():
    """
    获取所有用户的列表（含角色信息）。
    使用 LEFT JOIN 关联角色表，GROUP_CONCAT 将多个角色合并为一个字符串返回。
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute("""
            SELECT u.id, u.username, u.display_name, u.auth_type,
                   u.is_active, u.last_login, u.created_at,
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
            users.append(u)
    return users


@admin_router.post("/users")
def create_user(payload: dict):
    """
    创建新用户。
    请求体: {"username": "...", "password": "...", "display_name": "...",
             "auth_type": "local|ldap", "role_ids": [1, 2], "is_active": true}

    LDAP 用户可不填密码（由域控验证），本地用户必须填密码。
    """
    username = payload.get("username", "").strip()
    password = payload.get("password", "")
    display_name = payload.get("display_name", username)
    auth_type = payload.get("auth_type", "local")
    role_ids = payload.get("role_ids", [])
    is_active = payload.get("is_active", True)

    if not username or (auth_type == "local" and not password):
        raise HTTPException(status_code=400, detail="用户名和密码不能为空")

    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE username = ?", (username,))
        if c.fetchone():
            raise HTTPException(status_code=400, detail="用户名已存在")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        pw_hash = hash_password(password) if auth_type == "local" and password else None
        c.execute("""INSERT INTO users (username, password_hash, display_name, auth_type, is_active, created_at)
                     VALUES (?, ?, ?, ?, ?, ?)""",
                  (username, pw_hash, display_name, auth_type, int(is_active), now))
        uid = c.lastrowid

        for rid in role_ids:
            c.execute("INSERT OR IGNORE INTO user_roles (user_id, role_id) VALUES (?, ?)",
                      (uid, rid))
    return {"message": "用户创建成功", "id": uid}


@admin_router.put("/users/{user_id}")
def update_user(user_id: int, payload: dict):
    """
    编辑用户信息。
    可修改字段: display_name, is_active, password（留空不修改）, role_ids
    请求体只传需要修改的字段即可。
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE id = ?", (user_id,))
        if not c.fetchone():
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
    return {"message": "用户更新成功"}


@admin_router.delete("/users/{user_id}")
def delete_user(user_id: int, request: Request):
    """
    删除用户。
    不允许删除自己（request.state.user_id 来自 AuthMiddleware）。
    ON DELETE CASCADE 会自动清除关联的 user_roles 记录。
    """
    if int(request.state.user_id) == user_id:
        raise HTTPException(status_code=400, detail="不能删除自己的账号")

    with get_db() as conn:
        c = conn.cursor()
        c.execute("DELETE FROM users WHERE id = ?", (user_id,))
    return {"message": "用户已删除"}


# ============================================================
# 管理路由 — 角色管理（需 roles:manage 权限）
# ============================================================

@admin_router.get("/roles")
def list_roles():
    """获取所有角色及其拥有的权限列表。"""
    with get_db() as conn:
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
    return roles


@admin_router.post("/roles")
def create_role(payload: dict):
    """
    创建自定义角色。
    请求体: {"name": "自定义角色", "description": "...", "permission_ids": [1, 2, 3]}
    """
    name = payload.get("name", "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="角色名不能为空")
    desc = payload.get("description", "")
    perm_ids = payload.get("permission_ids", [])

    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT id FROM roles WHERE name = ?", (name,))
        if c.fetchone():
            raise HTTPException(status_code=400, detail="角色名已存在")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        c.execute("INSERT INTO roles (name, description, is_system, created_at) VALUES (?, ?, 0, ?)",
                  (name, desc, now))
        rid = c.lastrowid
        for pid in perm_ids:
            c.execute("INSERT OR IGNORE INTO role_permissions (role_id, permission_id) VALUES (?, ?)",
                      (rid, pid))
    return {"message": "角色创建成功", "id": rid}


@admin_router.put("/roles/{role_id}")
def update_role(role_id: int, payload: dict):
    """
    编辑角色（含权限分配）。
    系统预置角色的 name 不可修改，但权限可调整。
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM roles WHERE id = ?", (role_id,))
        row = c.fetchone()
        if not row:
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
    return {"message": "角色更新成功"}


@admin_router.delete("/roles/{role_id}")
def delete_role(role_id: int):
    """
    删除角色。
    系统预置角色（is_system=1）不可删除，防止误删导致管理员失去权限。
    """
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT is_system FROM roles WHERE id = ?", (role_id,))
        row = c.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="角色不存在")
        if row["is_system"]:
            raise HTTPException(status_code=400, detail="系统预置角色不可删除")
        c.execute("DELETE FROM roles WHERE id = ?", (role_id,))
    return {"message": "角色已删除"}


@admin_router.get("/permissions")
def list_permissions():
    """获取所有可用的权限项列表（供角色管理页面渲染勾选框）。"""
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT * FROM permissions ORDER BY id")
        return [dict(row) for row in c.fetchall()]


# ============================================================
# ASGI 中间件 — 请求拦截层
# 所有 /api/* 请求进入路由函数之前，都会先经过此中间件
# ============================================================

class AuthMiddleware(BaseHTTPMiddleware):
    """
    JWT 鉴权 + RBAC 权限检查中间件。

    处理流程:
      1. 白名单放行 — /api/auth/login 和 /api/auth/refresh 不需要鉴权
      2. 非 /api/ 路径放行 — 静态文件、页面路由等
      3. 提取 Authorization: Bearer <token> 请求头
      4. 验证 JWT 签名 + 过期 + token 类型（必须是 access，不能用 refresh）
      5. 查询用户权限，注入 request.state（供后续路由使用）
      6. 检查用户是否被禁用
      7. 匹配路由所需的权限，不满足返回 403
      8. 全部通过 → 放行到路由函数
    """

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method

        # ---- 步骤 1: 白名单放行 ----
        if path in ("/api/auth/login", "/api/auth/refresh"):
            return await call_next(request)

        # ---- 步骤 2: 非 API 路径放行 ----
        if not path.startswith("/api/"):
            return await call_next(request)

        # ---- 步骤 3: 提取 token ----
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            return JSONResponse(status_code=401, content={"detail": "缺少认证 token"})

        token = auth_header[7:]   # 去掉 "Bearer " 前缀（7 个字符）

        # ---- 步骤 4: 验证 JWT ----
        try:
            payload = verify_token(token)
            if payload.get("type") != "access":   # 拒绝 refresh token
                return JSONResponse(status_code=401, content={"detail": "请使用 access token"})
        except HTTPException as e:
            return JSONResponse(status_code=e.status_code, content={"detail": e.detail})
        except Exception:
            return JSONResponse(status_code=401, content={"detail": "token 无效"})

        # ---- 步骤 5: 注入用户信息到 request.state ----
        user_id = int(payload["sub"])
        request.state.user_id = user_id
        request.state.username = payload["username"]
        request.state.user_permissions = get_user_permissions(user_id)

        # ---- 步骤 6: 检查用户是否被禁用 ----
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT is_active FROM users WHERE id = ?", (user_id,))
            row = c.fetchone()
            if not row or not row["is_active"]:
                return JSONResponse(status_code=403, content={"detail": "账号已被禁用"})

        # ---- 步骤 7: RBAC 权限检查 ----
        required_perm = self._match_permission(method, path)
        if required_perm and required_perm not in request.state.user_permissions:
            logger.warning("权限拒绝 user=%s path=%s %s required=%s",
                          request.state.username, method, path, required_perm)
            return JSONResponse(status_code=403, content={"detail": f"需要权限: {required_perm}"})

        # ---- 步骤 8: 放行 ----
        return await call_next(request)

    @staticmethod
    def _match_permission(method: str, path: str) -> str | None:
        """
        将请求路径与 ROUTE_PERMISSIONS 表进行匹配。
        先精确匹配，再前缀匹配（处理 /api/users/3 这种带路径参数的 URL）。

        例如:
          请求 PUT /api/users/5
          → 精确匹配失败（表中是 PUT /api/users/{id}）
          → 前缀匹配：比较每一段，{id} 匹配任意值 → 返回 "users:manage"
        """
        # 精确匹配
        key = (method, path)
        if key in ROUTE_PERMISSIONS:
            return ROUTE_PERMISSIONS[key]

        # 前缀匹配：逐段比较，{xxx} 视为通配符
        path_parts = path.rstrip("/").split("/")
        for (m, pattern), perm in ROUTE_PERMISSIONS.items():
            if m != method:
                continue
            pattern_parts = pattern.rstrip("/").split("/")
            if len(path_parts) != len(pattern_parts):   # 段数不同，不可能匹配
                continue
            match = True
            for pp, pt in zip(path_parts, pattern_parts):
                if pt.startswith("{") and pt.endswith("}"):
                    continue   # 路径参数（如 {id}）匹配任意值
                if pp != pt:
                    match = False
                    break
            if match:
                return perm
        return None
