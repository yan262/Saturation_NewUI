"""
数据库工具模块
==============
提供 SQLite 数据库连接上下文管理器，确保连接在使用后自动关闭。

使用方式:
    from database import get_db
    with get_db() as conn:
        c = conn.cursor()
        c.execute("SELECT ...")
        rows = c.fetchall()
"""

import sqlite3
import os
import sys
from contextlib import contextmanager
from typing import Generator

# 数据库路径 — 与 server.py 共享同一个 SQLite
# 可通过 DATABASE_PATH 环境变量覆盖（测试用）
_forced_path = os.getenv("DATABASE_PATH", "")
if _forced_path:
    DB_DIR = os.path.dirname(_forced_path)
    DB_NAME = os.path.basename(_forced_path)
elif getattr(sys, 'frozen', False):
    BASE_DIR = os.path.dirname(sys.executable)
    DB_DIR = os.path.join(BASE_DIR, "data")
    DB_NAME = "saturation.db"
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    DB_DIR = os.path.join(BASE_DIR, "data")
    DB_NAME = "saturation.db"


def get_db_path() -> str:
    """返回 SQLite 数据库文件的完整路径。"""
    os.makedirs(DB_DIR, exist_ok=True)
    return os.path.join(DB_DIR, DB_NAME)


@contextmanager
def get_db(row_factory: bool = True) -> Generator[sqlite3.Connection, None, None]:
    """SQLite 数据库连接上下文管理器。

    参数:
        row_factory — True 时启用 sqlite3.Row，使查询结果支持字典式访问。

    使用示例:
        with get_db() as conn:
            c = conn.cursor()
            c.execute("SELECT * FROM users")
            rows = c.fetchall()
        # 离开 with 块时自动 conn.commit() + conn.close()
    """
    conn = sqlite3.connect(get_db_path())
    if row_factory:
        conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
