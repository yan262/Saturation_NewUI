"""
应用配置文件
============
所有配置项支持两种方式设置（优先级从高到低）：
  1. 环境变量（推荐生产环境使用）
  2. 下方默认值（仅适用本地开发）

敏感信息（OneNet 凭证、JWT 密钥）不应硬编码在此文件中，
请复制 .env.example 为 .env 并填写真实值。
"""

import os

# 尝试加载 .env 文件（python-dotenv 为可选依赖）
try:
    from dotenv import load_dotenv
    load_dotenv(override=False)
except ImportError:
    # python-dotenv 未安装时，手动解析 .env 文件
    _env_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if os.path.isfile(_env_file):
        with open(_env_file, "r", encoding="utf-8") as _f:
            for _line in _f:
                _line = _line.strip()
                if not _line or _line.startswith("#") or "=" not in _line:
                    continue
                _key, _, _val = _line.partition("=")
                _key = _key.strip()
                _val = _val.strip().strip('"').strip("'")
                if _key and _key not in os.environ:
                    os.environ[_key] = _val


def _env(key: str, default: str = "") -> str:
    """读取环境变量，未设置时返回默认值。"""
    return os.getenv(key, default)


# ============================================================
# OneNet IoT 平台配置 — 通过环境变量设置
# ============================================================
PRODUCT_ID = _env("ONENET_PRODUCT_ID", "")
DEVICE_NAME = _env("ONENET_DEVICE_NAME", "")
TOKEN = _env("ONENET_TOKEN", "")

# ============================================================
# 服务配置
# ============================================================
HOST = _env("HOST", "0.0.0.0")
PORT = int(_env("PORT", "8000"))

# ============================================================
# 默认设置
# ============================================================
REFRESH_RATE = int(_env("REFRESH_RATE", "2"))
ALARM_THRESHOLD = float(_env("ALARM_THRESHOLD", "85"))

# ============================================================
# 认证配置
# ============================================================
JWT_SECRET = _env("JWT_SECRET", "")
JWT_ALGORITHM = _env("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(_env("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))
REFRESH_TOKEN_EXPIRE_DAYS = int(_env("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

# ============================================================
# LDAP/AD 配置（可选）
# ============================================================
LDAP_ENABLED = _env("LDAP_ENABLED", "False").lower() in ("true", "1", "yes")
LDAP_SERVER = _env("LDAP_SERVER", "ldap://your-ad-server:389")
LDAP_BASE_DN = _env("LDAP_BASE_DN", "dc=company,dc=com")
LDAP_DOMAIN = _env("LDAP_DOMAIN", "COMPANY")


# ============================================================
# 启动时安全检查
# ============================================================
def _check_config():
    """启动时校验关键配置，打印警告而非阻止启动。"""
    global JWT_SECRET
    warnings = []

    if not PRODUCT_ID:
        warnings.append("ONENET_PRODUCT_ID 未设置 — 无法连接 OneNet 平台")
    if not DEVICE_NAME:
        warnings.append("ONENET_DEVICE_NAME 未设置 — 无法连接 OneNet 平台")
    if not TOKEN:
        warnings.append("ONENET_TOKEN 未设置 — 无法连接 OneNet 平台")
    if not JWT_SECRET:
        warnings.append(
            "JWT_SECRET 未设置 — 使用随机生成的密钥（重启后所有用户需重新登录）。"
            "生产环境请在 .env 中设置固定值。"
        )
        # 自动生成随机密钥作为兜底，同时更新模块变量和环境变量
        import secrets
        JWT_SECRET = secrets.token_urlsafe(32)
        os.environ["JWT_SECRET"] = JWT_SECRET

    if warnings:
        print()
        print("=" * 60)
        print("  ⚠  Configuration warnings:")
        for w in warnings:
            print(f"     - {w}")
        print("  See .env.example for reference.")
        print("=" * 60)
        print()


_check_config()
