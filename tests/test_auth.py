"""
auth 模块单元测试
=================
覆盖密码哈希、JWT 签发/验证、权限查询、数据库初始化等核心功能。

运行方式:
    cd 项目根目录
    python -m pytest tests/test_auth.py -v
    python -m pytest tests/test_auth.py -v --cov=auth --cov-report=term-missing
"""

import os
import sys
import tempfile
import shutil
import pytest
from unittest.mock import patch

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(autouse=True)
def temp_db(monkeypatch):
    """每个测试使用独立的临时数据库，互不干扰。"""
    tmpdir = tempfile.mkdtemp()
    db_path = os.path.join(tmpdir, "test_saturation.db")
    monkeypatch.setenv("DATABASE_PATH", db_path)

    # 由于 database.py / auth.py 可能在 fixture 调用前已被导入，
    # 需要手动使 DATABASE_PATH 生效 —— 重新加载 database 模块
    import database
    database.DB_DIR = os.path.dirname(db_path)
    database.DB_NAME = os.path.basename(db_path)
    os.makedirs(os.path.dirname(db_path), exist_ok=True)

    yield db_path

    # 测试后清理
    if os.path.exists(db_path):
        os.remove(db_path)
    shutil.rmtree(tmpdir, ignore_errors=True)


@pytest.fixture
def auth_module(temp_db):
    """导入 auth 模块（延迟导入以确保 monkeypatch 先生效）。"""
    import auth
    # 确保使用临时数据库进行初始化
    auth.init_auth_db()
    return auth


# ============================================================
# 密码哈希测试
# ============================================================

class TestPasswordHashing:
    """bcrypt 密码哈希和验证。"""

    def test_hash_returns_string(self, auth_module):
        result = auth_module.hash_password("hello123")
        assert isinstance(result, str)
        assert result.startswith("$2b$") or result.startswith("$2a$")

    def test_hash_is_deterministic_per_call(self, auth_module):
        """每次哈希应生成不同的 salt，结果不同。"""
        h1 = auth_module.hash_password("same-pass")
        h2 = auth_module.hash_password("same-pass")
        assert h1 != h2

    def test_verify_correct_password(self, auth_module):
        hashed = auth_module.hash_password("secret123")
        assert auth_module.verify_password("secret123", hashed) is True

    def test_verify_wrong_password(self, auth_module):
        hashed = auth_module.hash_password("secret123")
        assert auth_module.verify_password("wrongpass", hashed) is False

    def test_verify_empty_password(self, auth_module):
        hashed = auth_module.hash_password("")
        assert auth_module.verify_password("", hashed) is True
        assert auth_module.verify_password("x", hashed) is False

    def test_verify_unicode_password(self, auth_module):
        pwd = "密码测试123!@#"
        hashed = auth_module.hash_password(pwd)
        assert auth_module.verify_password(pwd, hashed) is True


# ============================================================
# JWT 测试
# ============================================================

class TestJWT:
    """JWT token 签发和验证。"""

    def test_create_access_token(self, auth_module):
        token = auth_module.create_access_token(1, "admin")
        assert isinstance(token, str)
        # JWT 由 3 段 base64 组成，用 . 分隔
        assert token.count(".") == 2

    def test_create_refresh_token(self, auth_module):
        token = auth_module.create_refresh_token(1, "admin")
        assert isinstance(token, str)
        assert token.count(".") == 2

    def test_verify_access_token(self, auth_module):
        token = auth_module.create_access_token(1, "testuser")
        payload = auth_module.verify_token(token)
        assert payload["sub"] == "1"
        assert payload["username"] == "testuser"
        assert payload["type"] == "access"

    def test_verify_refresh_token(self, auth_module):
        token = auth_module.create_refresh_token(2, "operator")
        payload = auth_module.verify_token(token)
        assert payload["sub"] == "2"
        assert payload["username"] == "operator"
        assert payload["type"] == "refresh"

    def test_verify_invalid_token(self, auth_module):
        from fastapi import HTTPException
        with pytest.raises(HTTPException) as exc:
            auth_module.verify_token("not.a.valid.token")
        assert exc.value.status_code == 401
        assert "无效" in exc.value.detail

    def test_access_token_contains_expiry(self, auth_module):
        token = auth_module.create_access_token(1, "admin")
        payload = auth_module.verify_token(token)
        assert "exp" in payload

    def test_refresh_token_has_longer_expiry(self, auth_module):
        """refresh token 的过期时间应比 access token 长。"""
        import jwt as pyjwt
        access = pyjwt.decode(
            auth_module.create_access_token(1, "admin"),
            auth_module.JWT_SECRET, algorithms=[auth_module.JWT_ALGORITHM],
            options={"verify_exp": False}
        )
        refresh = pyjwt.decode(
            auth_module.create_refresh_token(1, "admin"),
            auth_module.JWT_SECRET, algorithms=[auth_module.JWT_ALGORITHM],
            options={"verify_exp": False}
        )
        # refresh 过期时间 > access 过期时间（单位：秒）
        assert refresh["exp"] > access["exp"]


# ============================================================
# 权限查询测试
# ============================================================

class TestPermissions:
    """RBAC 权限查询。"""

    def test_admin_has_all_permissions(self, auth_module):
        """默认管理员（admin）应拥有全部 6 个预置权限。"""
        with auth_module.get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT id FROM users WHERE username = 'admin'")
            admin_id = c.fetchone()["id"]

        perms = auth_module.get_user_permissions(admin_id)
        assert len(perms) == 6
        assert "dashboard:view" in perms
        assert "settings:write" in perms
        assert "data:export" in perms
        assert "users:manage" in perms
        assert "roles:manage" in perms
        assert "alarms:view" in perms

    def test_nonexistent_user_has_no_permissions(self, auth_module):
        perms = auth_module.get_user_permissions(99999)
        assert perms == set()

    def test_readonly_user_permissions(self, auth_module):
        """只读用户应该只有 dashboard:view 和 alarms:view。"""
        from datetime import datetime
        with auth_module.get_db() as conn:
            c = conn.cursor()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            c.execute(
                "INSERT INTO users (username, display_name, auth_type, created_at) VALUES (?, ?, 'local', ?)",
                ("readonly", "只读测试", now))
            uid = c.lastrowid
            c.execute("SELECT id FROM roles WHERE name = '只读用户'")
            rid = c.fetchone()["id"]
            c.execute("INSERT INTO user_roles (user_id, role_id) VALUES (?, ?)", (uid, rid))

        perms = auth_module.get_user_permissions(uid)
        assert perms == {"dashboard:view", "alarms:view"}


# ============================================================
# 数据库初始化测试
# ============================================================

class TestDBInit:
    """数据库初始化（init_auth_db）。"""

    def test_init_creates_tables(self, auth_module):
        """初始化应创建 5 张核心表。"""
        with auth_module.get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")
            tables = {row["name"] for row in c.fetchall()}
            expected = {"users", "roles", "permissions", "user_roles", "role_permissions"}
            assert expected.issubset(tables)

    def test_init_is_idempotent(self, auth_module):
        """重复调用 init_auth_db 不报错，不重复创建。"""
        auth_module.init_auth_db()  # 首次
        auth_module.init_auth_db()  # 再次
        auth_module.init_auth_db()  # 再三
        # 不应有异常
        with auth_module.get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM users WHERE username = 'admin'")
            assert c.fetchone()[0] == 1  # 只有一个 admin

    def test_default_admin_exists(self, auth_module):
        with auth_module.get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM users WHERE username = 'admin'")
            admin = c.fetchone()
            assert admin is not None
            assert admin["display_name"] == "管理员"
            assert admin["auth_type"] == "local"
            assert admin["is_active"] == 1

    def test_admin_password_is_bcrypt(self, auth_module):
        with auth_module.get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT password_hash FROM users WHERE username = 'admin'")
            pw_hash = c.fetchone()["password_hash"]
            assert pw_hash.startswith("$2b$") or pw_hash.startswith("$2a$")
            # admin123 应能验证通过
            assert auth_module.verify_password("admin123", pw_hash) is True

    def test_preset_permissions_count(self, auth_module):
        with auth_module.get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM permissions")
            assert c.fetchone()[0] == 6

    def test_preset_roles_count(self, auth_module):
        with auth_module.get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT COUNT(*) FROM roles")
            assert c.fetchone()[0] == 3


# ============================================================
# LDAP 测试
# ============================================================

class TestLDAP:
    """LDAP 认证测试（无需实际 LDAP 服务器）。"""

    def test_ldap_disabled_returns_false(self, auth_module):
        assert auth_module.ldap_authenticate("anyuser", "anypass") is False

    def test_ldap_enabled_no_server(self, auth_module):
        with patch.object(auth_module, "LDAP_ENABLED", True):
            result = auth_module.ldap_authenticate("user", "pass")
            assert result is False  # 连接失败应返回 False 而非抛异常
