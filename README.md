# 电缆桥架饱和度监控系统

基于 **FastAPI + 纯前端 + OneNet 物联网云平台** 的实时监控仪表板，集成 **JWT 登录认证 + RBAC 角色权限管理**，支持本地账号和 LDAP/AD 双模式登录。

---

## 方式一：exe 安装包（推荐，无需装 Python）

适用于 **Windows 用户**，像普通软件一样下载、双击、使用。

### 打包为 exe（开发者操作）

在项目根目录下运行打包脚本：

```bash
python build_exe.py
```

完成后在 `dist/` 目录下得到 **电缆桥架饱和度监控.exe**（约 35 MB）。

### 发送给用户

将以下两个文件发给对方（放在同一个文件夹里）：

| 文件 | 作用 |
|------|------|
| `SaturationMonitor.exe` | 主程序 |
| `启动.bat` | 启动脚本（**双击这个**） |

使用步骤：

| 步骤 | 操作 |
|------|------|
| 1 | 双击 `启动.bat` |
| 2 | 弹出命令行窗口，显示启动信息 |
| 3 | 浏览器自动打开 `http://localhost:8000` |
| 4 | 输入账号 `admin`，密码 `admin123` 登录 |
| 5 | 关闭命令行窗口即可退出程序 |

> ⚠️ **务必双击 `启动.bat` 而不是直接点 exe** — bat 脚本会保持窗口不闪退，出错时能看到提示。  
> ⚠️ 首次启动安全软件可能弹窗提示，选择"允许运行"即可。  
> ⚠️ 如果端口被占用，窗口中会显示 `[FAIL]` 及解决方法。  
> ⚠️ exe 所在目录会自动创建 `data/` 文件夹存储数据库。

---

## 方式二：Docker 部署（推荐生产环境）

适用于服务器部署、Linux/macOS/Windows 均支持。

### 第一步：准备配置

```bash
cp .env.example .env
# 编辑 .env 填入你的 OneNet 凭证和 JWT 密钥
```

### 第二步：启动容器

```bash
docker compose up -d
```

### 第三步：访问

浏览器打开 **http://localhost:8000**。

> 💡 数据库文件存储在 `./data/` 目录（通过 volume 挂载），容器重启/重建数据不丢失。  
> 💡 修改 `docker-compose.yml` 中的端口映射可更改对外端口。  
> 💡 使用 `docker compose logs -f app` 查看实时日志。

---

## 方式三：源码启动（开发者 / 需改配置）

适用于需要修改配置、二次开发、或在 Linux/macOS 上运行。

### 环境要求

| 依赖 | 版本 |
|------|------|
| Python | ≥ 3.10 |
| pip | 随 Python 自带 |
| 网络 | 需要访问互联网（Google Fonts CDN + Chart.js CDN + OneNet API） |

所有操作系统（Windows / macOS / Linux）均可运行。

### 第一步：安装 Python 依赖

在项目根目录下打开终端，执行：

```bash
pip install -r requirements.txt
```

### 第二步：修改 OneNet 设备配置

编辑 `config.py`，将以下三项改为你的 OneNet 设备信息：

```python
PRODUCT_ID = "你的产品ID"
DEVICE_NAME = "你的设备名称"
TOKEN = "你的鉴权Token"
```

> 这三项从 OneNet 物联网平台控制台 → 设备详情页获取。

### 第三步：启动服务

```bash
python server.py
```

看到以下输出说明启动成功：

```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
```

---

## 访问系统

浏览器打开 **http://localhost:8000**，看到登录页面。

| 项目 | 值 |
|------|-----|
| 默认管理员账号 | `admin` |
| 默认管理员密码 | `admin123` |

> ⚠️ 首次登录后建议立即修改密码：登录 → 进入仪表板（暂不支持前端修改密码，可通过 API 修改，见下方 API 文档）。

---

## 系统流程

```
打开 http://localhost:8000
        │
        ▼
   ┌─────────────┐
   │  登录页面     │ ← 选择 本地账号 / LDAP·AD，输入用户名密码
   └──────┬──────┘
          │ 登录成功
          ▼
   ┌─────────────┐
   │  监控仪表板   │ ← 实时饱和度、趋势图、统计、报警日志
   │              │ ← 管理员可点击顶栏 "🔑 管理" 进入用户/角色管理
   └─────────────┘
```

---

## 用户权限说明

系统预置 **3 种角色**，创建用户时可分配不同角色：

| 角色 | 权限 |
|------|------|
| **超级管理员** | 全部功能：仪表板、修改设置、导出数据、用户管理、角色管理、报警日志 |
| **运维工程师** | 仪表板、修改设置、导出数据、报警日志 |
| **只读用户** | 仅查看仪表板和报警日志 |

管理员可自定义新角色，为每个角色灵活勾选权限项。

---

## 认证方式：本地账号 vs LDAP/AD

系统支持两种用户认证方式，创建用户时可选择：

| 对比维度 | 本地账号 | LDAP / AD |
|---------|---------|-----------|
| **密码存储** | 密码经 bcrypt 哈希后存在本地 SQLite 数据库 | 密码不在本地存储，由企业域控服务器验证 |
| **验证流程** | 用户输入密码 → 与数据库中的 bcrypt 哈希比对 | 用户输入密码 → 系统向 LDAP/AD 服务器发起绑定请求 → 域控返回验证结果 |
| **适用场景** | 没有域控环境的小团队、临时账号、外部访客 | 已部署 Active Directory 或 LDAP 的企业内部员工 |
| **密码修改** | 可在系统内自助修改（需原密码） | 在域控服务器上修改（如 Windows 域密码策略），本系统不管理 |
| **账号创建** | 管理员在后台填写用户名和密码 | 管理员只需填写用户名（与域账号一致），无需填密码 |
| **优势** | 不依赖外部服务，开箱即用 | 统一身份认证，员工用域账号即可登录，无需记忆额外密码；离职后域账号禁用即自动失去访问权限 |
| **依赖条件** | 无额外依赖 | 需 `config.py` 中启用 `LDAP_ENABLED = True` 并填写域控服务器地址 |

**推荐用法：**
- 管理员给自己创建**本地账号**作为兜底（防止 LDAP 服务器故障时无法登录）
- 日常员工统一使用 **LDAP/AD 账号**，实现单点登录和安全策略统一管理

> ⚠️ LDAP 用户也需要在本地数据库中有一条记录（由管理员创建），登录时系统先通过域控验证密码，再查本地数据库确认用户存在且未被禁用。

---

---

## ⚠️ 弃用通知

`dashboard.py`（Streamlit 版）已弃用，不再接收功能更新。请使用 FastAPI 版本：`python server.py` → `http://localhost:8000`。Streamlit 版将在后续大版本中移除。

---

## 功能一览

| 功能 | 说明 |
|------|------|
| 🔐 登录认证 | 本地账号 + LDAP/AD 双模式，JWT 双 token 自动续期 |
| 🎯 实时监控 | WebSocket 推送实时饱和度数据 |
| 📊 仪表盘 | 240° 弧形霓虹仪表盘 + 实时数值卡片 |
| 📈 趋势图 | 最近 50 条数据的面积趋势图（Chart.js） |
| 📋 统计卡 | 平均值 / 最大值 / 最小值 / 采样次数 |
| ⚠ 报警日志 | 超过阈值自动触发，页面顶部红色呼吸灯 |
| 📥 CSV 导出 | 一键导出全部历史数据 |
| ⚙ 在线设置 | 调整刷新频率和报警阈值 |
| 👥 用户管理 | 创建/编辑/删除用户，分配角色 |
| 🔑 角色管理 | 自定义角色，灵活勾选权限 |
| ✨ 粒子背景 | 全屏科技感动画 |

---

## 配置文件说明

`config.py` 包含所有可配置项：

```python
# ── OneNet 物联网平台配置（必须修改）──
PRODUCT_ID = "你的产品ID"        # OneNet 产品 ID
DEVICE_NAME = "你的设备名称"     # OneNet 设备名称
TOKEN = "你的鉴权Token"          # OneNet API 鉴权 token

# ── 服务配置 ──
HOST = "0.0.0.0"                 # 监听地址，0.0.0.0 表示允许局域网访问
PORT = 8000                      # 监听端口

# ── 默认设置 ──
REFRESH_RATE = 2                 # 数据刷新间隔（秒）
ALARM_THRESHOLD = 85             # 报警阈值（%）

# ── JWT 认证配置 ──
JWT_SECRET = "修改为随机字符串"   # ★ 生产环境务必修改，用于签名 JWT token
JWT_ALGORITHM = "HS256"          # 签名算法
ACCESS_TOKEN_EXPIRE_MINUTES = 30 # access token 有效期（分钟）
REFRESH_TOKEN_EXPIRE_DAYS = 7    # refresh token 有效期（天）

# ── LDAP/AD 配置（可选）──
LDAP_ENABLED = False             # True 为启用 LDAP 认证
LDAP_SERVER = "ldap://服务器地址:389"
LDAP_BASE_DN = "dc=company,dc=com"
LDAP_DOMAIN = "COMPANY"          # AD 域名
```

---

## 目录结构

```
项目根目录/
│
├── server.py              # FastAPI 后端主程序（API + WebSocket + 静态文件）
├── auth.py                # 认证与 RBAC 模块（JWT/LDAP/权限/中间件）
├── config.py              # ★ 配置文件（修改 OneNet 凭证 + JWT 密钥）
├── requirements.txt       # Python 依赖清单
├── build_exe.py           # 打包脚本（生成独立 .exe）
│
├── static/                # 前端文件
│   ├── login.html         # 登录页面（左右分栏全屏布局）
│   ├── index.html         # 监控仪表板（含管理面板）
│   ├── css/
│   │   └── style.css      # 全局样式（暗色科技风）
│   └── js/
│       ├── auth.js        # 认证工具（token 管理、自动刷新、登录守卫）
│       ├── admin.js       # 管理面板（用户管理 + 角色管理）
│       ├── app.js         # 仪表板主逻辑（WebSocket、图表、UI）
│       ├── gauge.js       # 弧形仪表盘渲染
│       └── particles.js   # 粒子背景动画
│
├── data/                  # SQLite 数据库目录（自动创建）
│   └── saturation.db      # 历史数据 + 用户/角色/权限表
│
└── docs/                  # 设计文档
    └── superpowers/
        ├── specs/         # 需求设计文档
        └── plans/         # 实施计划文档
```

---

## API 文档

启动服务后访问 **http://localhost:8000/docs** 查看完整的 Swagger 自动生成的 API 文档。

### 主要 API 端点

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| POST | `/api/auth/login` | 无 | 登录 |
| POST | `/api/auth/refresh` | 无 | 刷新 token |
| GET | `/api/auth/me` | 登录 | 当前用户信息 |
| PUT | `/api/auth/password` | 登录 | 修改自己密码 |
| GET | `/api/saturation/current` | dashboard:view | 实时饱和度 |
| GET | `/api/saturation/history` | dashboard:view | 历史数据 |
| GET | `/api/saturation/stats` | dashboard:view | 统计信息 |
| GET | `/api/alarm/logs` | alarms:view | 报警日志 |
| GET | `/api/export/csv` | data:export | 导出 CSV |
| PUT | `/api/settings` | settings:write | 修改设置 |
| GET | `/api/users` | users:manage | 用户列表 |
| POST | `/api/users` | users:manage | 创建用户 |
| PUT | `/api/users/{id}` | users:manage | 编辑用户 |
| DELETE | `/api/users/{id}` | users:manage | 删除用户 |
| GET | `/api/roles` | roles:manage | 角色列表 |
| POST | `/api/roles` | roles:manage | 创建角色 |
| PUT | `/api/roles/{id}` | roles:manage | 编辑角色 |
| DELETE | `/api/roles/{id}` | roles:manage | 删除角色 |
| GET | `/api/permissions` | roles:manage | 权限列表 |
| WS | `/ws` | dashboard:view | WebSocket 实时推送（token 通过 Sec-WebSocket-Protocol 子协议传递）|

---

## 常见问题

**Q: 启动报 `ModuleNotFoundError: No module named 'xxx'`？**

A: 未安装依赖，执行 `pip install -r requirements.txt`。

**Q: 页面显示"⬡ 断开"，没有数据？**

A: 检查 `config.py` 中的 OneNet 凭证（PRODUCT_ID、DEVICE_NAME、TOKEN）是否正确，设备是否在线。

**Q: 登录页字体显示异常（乱码/缺字）？**

A: 字体文件已本地化存储在 `static/fonts/` 目录，无需网络即可正常显示。如果仍有问题，检查 `static/css/fonts.css` 是否存在。

**Q: 端口 8000 被占用？**

A: 修改 `config.py` 中的 `PORT` 为其他值（如 8080），重新启动。

**Q: 忘记管理员密码怎么办？**

A: 删除 `data/saturation.db` 文件后重启服务，系统会自动创建新的默认管理员 `admin/admin123`。⚠ 此操作会同时清空所有历史监控数据和用户数据。

**Q: 如何让局域网内其他电脑访问？**

A: `config.py` 中 `HOST = "0.0.0.0"` 已默认允许。其他电脑访问 `http://<本机IP>:8000` 即可。注意防火墙可能需要放行 8000 端口。

**Q: 如何启用 LDAP/AD 登录？**

A: 编辑 `config.py`，设置 `LDAP_ENABLED = True` 并填写正确的 `LDAP_SERVER`、`LDAP_BASE_DN`、`LDAP_DOMAIN`。然后重启服务。

**Q: JWT_SECRET 需要改吗？**

A: 仅本地测试可用默认值。部署到生产或公网环境务必修改为随机长字符串。
