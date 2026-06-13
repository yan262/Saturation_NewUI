# 登录 & RBAC 权限系统 — 设计文档

日期: 2026-06-12

## 1. 目标

为电缆桥架饱和度监控平台添加企业级身份认证和可配置 RBAC 权限控制，支持本地账号 + LDAP/AD 双模式登录，不引入外部独立服务。

## 2. 文件结构

```
（项目根目录）
├── server.py              # [修改] 挂载 auth_router + Middleware，WebSocket token 鉴权
├── auth.py                # [新建] 认证模块（唯一新增后端文件）
├── config.py              # [修改] 新增 JWT_SECRET, LDAP_SERVER 等配置项
├── requirements.txt       # [修改] 新增 pyjwt, bcrypt, ldap3 依赖
│
└── static/
    ├── login.html         # [新建] 登录页
    ├── index.html         # [修改] 仪表板页头加管理入口 + token 检查
    ├── css/
    │   └── style.css      # [修改] 追加登录页/管理面板样式
    └── js/
        ├── auth.js        # [新建] token 存储/刷新/401 拦截
        ├── admin.js       # [新建] 用户管理 + 角色管理面板逻辑
        ├── app.js         # [修改] WebSocket 携带 token；启动时检查登录状态
        ├── gauge.js       # 不变
        └── particles.js   # 不变
```

**新增文件数: 4**（auth.py, login.html, auth.js, admin.js）  
**修改文件数: 5**（server.py, config.py, requirements.txt, index.html, app.js, style.css）

> 说明：`admin.html` 不单独拆分，用户管理和角色管理内嵌在 `index.html` 中作为隐藏面板（点击顶栏"管理"按钮展开），减少文件碎片。

## 3. 数据库新增表（SQLite 同库）

所有表添加到现有 `data/saturation.db`，由 `auth.py` 的 `init_auth_db()` 自动建表。

### 3.1 表结构

**users**
| 列 | 类型 | 说明 |
|----|------|------|
| id | INTEGER PK | 自增 |
| username | TEXT UNIQUE | 登录名 |
| password_hash | TEXT | bcrypt 哈希（本地账号） |
| display_name | TEXT | 显示名称 |
| auth_type | TEXT | `local` 或 `ldap` |
| ldap_dn | TEXT | LDAP 专有名称，可为 NULL |
| is_active | INTEGER | 0=禁用 1=启用 |
| last_login | TEXT | 最后登录时间 |
| created_at | TEXT | 创建时间 |

**roles**
| 列 | 类型 | 说明 |
|----|------|------|
| id | INTEGER PK | 自增 |
| name | TEXT UNIQUE | 角色名 |
| description | TEXT | 描述 |
| is_system | INTEGER | 0=自定义 1=系统预置（不可删除） |
| created_at | TEXT | 创建时间 |

**permissions**
| 列 | 类型 | 说明 |
|----|------|------|
| id | INTEGER PK | 自增 |
| code | TEXT UNIQUE | 权限码，如 `dashboard:view` |
| name | TEXT | 中文名，如 "查看仪表板" |
| description | TEXT | 说明 |

**user_roles**
| 列 | 类型 |
|----|------|
| user_id | FK → users.id |
| role_id | FK → roles.id |

**role_permissions**
| 列 | 类型 |
|----|------|
| role_id | FK → roles.id |
| permission_id | FK → permissions.id |

### 3.2 预置数据

**预置权限**
| code | name |
|------|------|
| `dashboard:view` | 查看仪表板 |
| `settings:write` | 修改监控设置 |
| `data:export` | 导出 CSV |
| `users:manage` | 用户管理 |
| `roles:manage` | 角色权限管理 |
| `alarms:view` | 查看报警日志 |

**预置角色**
| name | 权限 | 系统 |
|------|------|------|
| 超级管理员 | 全部 6 项 | 是 |
| 运维工程师 | dashboard:view, settings:write, data:export, alarms:view | 是 |
| 只读用户 | dashboard:view, alarms:view | 是 |

**默认管理员**: 首次启动时自动创建 `admin / admin123`（超级管理员），首次登录后应强制修改密码。

## 4. auth.py 模块（后端唯一新增文件）

`auth.py` 包含以下内容，不新建子目录或 `__init__.py`：

```
auth.py 内部结构
├── 常量           JWT_SECRET, JWT_ALGORITHM, ACCESS_EXPIRE, REFRESH_EXPIRE
├── init_auth_db() 建表 + 预置数据 + 默认管理员
├── hash_password / verify_password  (bcrypt)
├── create_access_token / create_refresh_token / verify_token  (pyjwt)
├── ldap_authenticate(username, password) → bool  (ldap3)
├── get_user_permissions(user_id) → set[str]
├── require_permission(code)  — FastAPI 依赖注入，用于路由级 RBAC
├── APIRouter("auth")
│   ├── POST /api/auth/login
│   ├── POST /api/auth/refresh
│   ├── GET  /api/auth/me
│   └── PUT  /api/auth/password
├── APIRouter("admin")         ← 仅 users:manage / roles:manage 可访问
│   ├── GET    /api/users
│   ├── POST   /api/users
│   ├── PUT    /api/users/{id}
│   ├── DELETE /api/users/{id}
│   ├── GET    /api/roles
│   ├── POST   /api/roles
│   ├── PUT    /api/roles/{id}
│   ├── DELETE /api/roles/{id}
│   └── GET    /api/permissions
└── AuthMiddleware  (纯 ASGI 中间件，对所有 /api/* 路径拦截 JWT + RBAC)
```

**关键设计决定：**
- `auth_router` 挂载在 `app` 时 `prefix="/api/auth"`，`admin_router` 挂载 `prefix="/api"`，避免 URL 冲突
- `AuthMiddleware` 白名单放行 `/api/auth/*`，其余 `/api/*` 强制鉴权
- WebSocket `/ws` 的 token 通过 URL 参数 `?token=xxx` 传递，在 `server.py` 的 websocket handler 中手动调 `verify_token()`

## 5. API 端点

### 5.1 认证（无需鉴权）

| 方法 | 路径 | 请求体 | 返回 |
|------|------|--------|------|
| POST | `/api/auth/login` | `{username, password, auth_type}` | `{access_token, refresh_token, user}` |
| POST | `/api/auth/refresh` | `{refresh_token}` | `{access_token}` |

### 5.2 当前用户（需鉴权）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/auth/me` | 当前用户信息 + 权限列表 |
| PUT | `/api/auth/password` | 修改自己的密码 |

### 5.3 用户管理（需 `users:manage`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/users` | 用户列表 |
| POST | `/api/users` | 创建用户 |
| PUT | `/api/users/{id}` | 编辑用户（含角色分配） |
| DELETE | `/api/users/{id}` | 删除用户（不可删除自己） |

### 5.4 角色管理（需 `roles:manage`）

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/roles` | 角色列表 + 各角色拥有的权限 |
| POST | `/api/roles` | 创建自定义角色 |
| PUT | `/api/roles/{id}` | 编辑角色名 + 权限分配 |
| DELETE | `/api/roles/{id}` | 删除（is_system=1 的角色拒绝） |
| GET | `/api/permissions` | 所有可用权限列表 |

### 5.5 现有 API 鉴权

| 路径 | 所需权限 |
|------|----------|
| `/api/saturation/*` | `dashboard:view` |
| `/api/settings` (PUT) | `settings:write` |
| `/api/settings` (GET) | `dashboard:view` |
| `/api/export/csv` | `data:export` |
| `/api/alarm/logs` | `alarms:view` |
| `/ws` | `dashboard:view` |

## 6. 前端页面流

```
login.html ──(登录成功)──→ index.html (仪表板)
  ↑                              │
  │                     token 过期 / 401
  └────────────────────────────────┘
```

### 6.1 login.html（新建，独立页面）
- 全屏左右分栏布局
- 左侧 45%：品牌区（⚡ Logo、平台名、三条标语、v2.0 Enterprise）
- 右侧 55%：登录表单（认证方式标签切换、用户名、密码、发光登录按钮）
- 粒子动画覆盖全屏背景
- LDAP 模式下用户名 placeholder 变为"域账号"
- 登录失败显示红色错误提示

### 6.2 index.html（仪表板，修改）
- 顶栏添加"管理"按钮（仅拥有 `users:manage` 或 `roles:manage` 权限的用户可见）
- 页面加载时检查 token → 无 token 或已过期 → 跳转 login.html
- 新增隐藏管理面板区域（用户管理 / 角色管理标签页）

### 6.3 auth.js（新建）
- `getToken()` / `setToken()` — localStorage 读写
- `getAuthHeaders()` — 返回 `{Authorization: Bearer xxx}` 
- `refreshAccessToken()` — 用 refresh_token 换新 access_token
- `logout()` — 清除 token，跳转 login.html
- `fetchWithAuth(url, options)` — 封装 fetch，自动附带 token + 401 时自动刷新或跳登录

### 6.4 admin.js（新建）
- 绑定管理面板的标签切换、表格渲染、模态框
- 用户创建/编辑弹窗（用户名、显示名、认证方式、角色多选、启用开关）
- 角色创建/编辑弹窗（角色名、描述、权限勾选列表）
- 删除确认提示

## 7. 鉴权中间件流程

```
请求 /api/* → AuthMiddleware
    │
    ├─ 路径匹配 /api/auth/* ？ → 是 → 放行
    │
    ├─ Authorization header 缺失？ → 是 → 401
    │
    ├─ Bearer token 签名无效/过期？ → 是 → 401 {"detail":"token 已过期,请刷新"}
    │
    ├─ 用户 is_active=0 ？ → 是 → 403 {"detail":"账号已禁用"}
    │
    ├─ 路由需要权限码，用户不满足？ → 是 → 403 {"detail":"需要权限: xxx"}
    │
    └─ 放行 → 路由处理
```

## 8. 错误处理

| 场景 | HTTP | 响应 |
|------|------|------|
| 登录失败 | 401 | `{"detail":"用户名或密码错误"}` |
| LDAP 服务不可达 | 503 | `{"detail":"LDAP 服务不可用,请使用本地账号"}` |
| Token 过期 | 401 | `{"detail":"token 已过期"}` |
| 权限不足 | 403 | `{"detail":"需要权限: settings:write"}` |
| 删除自己 | 400 | `{"detail":"不能删除自己的账号"}` |
| 删除系统角色 | 400 | `{"detail":"系统预置角色不可删除"}` |

## 9. 不做的（YAGNI）

- 注册页面 — 用户由管理员后台创建
- 密码重置邮件 — 管理员直接重置
- MFA/TOTP — 内部系统无需
- 登录验证码 — JWT 限流已足够
- 文件上传/头像 — 无此需求
