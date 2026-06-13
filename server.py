"""
电缆桥架饱和度监控 — FastAPI 后端
===================================
提供 REST API + WebSocket，代理 OneNet IoT 平台数据采集，
SQLite 本地持久化历史记录和报警日志。

启动方式: python server.py
访问地址: http://localhost:8000
API 文档: http://localhost:8000/docs (FastAPI 自动生成)
"""

import asyncio
import os
import sys
import io
import logging
import webbrowser
import threading
from datetime import datetime
from contextlib import asynccontextmanager

import requests
import pandas as pd
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

# 日志配置
from logger import setup_logging
logger = logging.getLogger(__name__)

# ============================================================
# OneNet IoT 平台配置 — 在 config.py 中修改
# ============================================================
from config import PRODUCT_ID, DEVICE_NAME, TOKEN, HOST, PORT, REFRESH_RATE, ALARM_THRESHOLD

API_URL = "https://iot-api.heclouds.com/thingmodel/query-device-property"

# ============================================================
# 认证模块
# ============================================================
from auth import init_auth_db, auth_router, admin_router, AuthMiddleware, verify_token

# ============================================================
# 路径处理 — 兼容 PyInstaller 打包和源码运行
# ============================================================
if getattr(sys, 'frozen', False):
    # PyInstaller 打包后: 静态文件在临时解压目录，数据库放在 exe 同级目录
    BASE_DIR = os.path.dirname(sys.executable)
    STATIC_DIR = os.path.join(sys._MEIPASS, "static")
else:
    # 源码运行: 所有文件在项目根目录
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    STATIC_DIR = os.path.join(BASE_DIR, "static")

from database import get_db

# ============================================================
# 运行时设置 — 持久化到 SQLite，服务重启不丢失
# 前端可通过 PUT /api/settings 修改，立即生效
# ============================================================
settings = {
    "refresh_rate": REFRESH_RATE,       # 默认值，启动时会被数据库中的值覆盖
    "alarm_threshold": ALARM_THRESHOLD,
}


# ============================================================
# 数据库初始化
# ============================================================
def init_db():
    """首次运行时创建数据表（如已存在则跳过）。

    三张表:
      saturation_history — 所有饱和度读数（用于统计和导出）
      alarm_log         — 报警记录（仅记录超过阈值的数据点）
      system_settings   — 运行时设置持久化（刷新间隔、报警阈值）
    """
    with get_db(row_factory=False) as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS saturation_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                value REAL NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS alarm_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                value REAL NOT NULL,
                threshold REAL NOT NULL
            )
        """)
        c.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
        """)


def load_settings_from_db():
    """
    从数据库加载持久化的运行时设置。
    如果表中没有记录（首次启动），使用 config.py 的默认值并写入数据库。
    调用时机: 应用启动时（lifespan 中 init_db() 之后）。
    """
    with get_db(row_factory=False) as conn:
        c = conn.cursor()
        c.execute("SELECT key, value FROM system_settings")
        rows = {r[0]: r[1] for r in c.fetchall()}

        if not rows:
            # 首次启动: 用 config.py 默认值初始化
            c.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)",
                      ("refresh_rate", str(REFRESH_RATE)))
            c.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)",
                      ("alarm_threshold", str(ALARM_THRESHOLD)))
            settings["refresh_rate"] = REFRESH_RATE
            settings["alarm_threshold"] = ALARM_THRESHOLD
        else:
            # 从数据库加载已有设置
            settings["refresh_rate"] = int(rows.get("refresh_rate", REFRESH_RATE))
            settings["alarm_threshold"] = float(rows.get("alarm_threshold", ALARM_THRESHOLD))


def save_settings_to_db():
    """将当前运行时设置写入数据库（PUT /api/settings 调用时触发）。"""
    with get_db(row_factory=False) as conn:
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)",
                  ("refresh_rate", str(settings["refresh_rate"])))
        c.execute("INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)",
                  ("alarm_threshold", str(settings["alarm_threshold"])))


# ============================================================
# OneNet 数据采集
# ============================================================
def fetch_from_onenet():
    """调用 OneNet 物模型 API，读取设备的 Saturation（饱和度）属性值。

    返回值:
        float — 饱和度百分比（如 72.5）
        None  — 网络超时、API 异常或属性不存在

    流程:
        1. 发送 GET 请求到 OneNet 物模型查询接口
        2. 解析 JSON: {"code": 0, "data": [{"identifier": "...", "value": ...}]}
        3. 遍历属性列表，找到 identifier == "Saturation" 的记录
        4. 返回其 value（浮点数）
    """
    headers = {"Authorization": TOKEN}
    params = {"product_id": PRODUCT_ID, "device_name": DEVICE_NAME}
    try:
        resp = requests.get(API_URL, headers=headers, params=params, timeout=10)
        data = resp.json()
        if data.get("code") == 0:                        # code=0 表示 API 调用成功
            for prop in data.get("data", []):            # 遍历返回的属性数组
                if prop.get("identifier") == "Saturation":  # 找到饱和度属性
                    return float(prop.get("value", 0.0))    # 转为浮点数返回
            logger.warning("OneNet 返回数据中未找到 Saturation 属性")
        else:
            logger.warning("OneNet API 返回错误 code=%s msg=%s",
                           data.get("code"), data.get("msg", "未知"))
    except requests.exceptions.Timeout:
        logger.warning("OneNet API 请求超时")
    except requests.exceptions.ConnectionError:
        logger.warning("无法连接 OneNet API（网络不可达）")
    except Exception:
        logger.exception("OneNet 数据采集异常")
    return None


# ============================================================
# 数据持久化 — 写入 SQLite
# ============================================================
def save_reading(timestamp_str, value):
    """保存一条饱和度读数到数据库。如果超过阈值，同时写入报警日志。

    参数:
        timestamp_str — 完整时间字符串，如 "2026-06-12 14:30:05"
        value         — 饱和度百分比（float）
    """
    with get_db(row_factory=False) as conn:
        c = conn.cursor()
        # 始终写入历史表
        c.execute("INSERT INTO saturation_history (timestamp, value) VALUES (?, ?)",
                  (timestamp_str, value))
        # 超过阈值时额外写入报警日志
        if value >= settings["alarm_threshold"]:
            c.execute("INSERT INTO alarm_log (timestamp, value, threshold) VALUES (?, ?, ?)",
                      (timestamp_str, value, settings["alarm_threshold"]))


# ============================================================
# 历史数据查询
# ============================================================
def get_history(limit=50):
    """查询最近 N 条历史记录，按时间正序返回（最早排前）。

    返回格式: [{"time": "14:30:05", "value": 72.5}, ...]
    """
    with get_db(row_factory=False) as conn:
        c = conn.cursor()
        c.execute("SELECT timestamp, value FROM saturation_history ORDER BY id DESC LIMIT ?", (limit,))
        rows = c.fetchall()
    return [{"time": r[0], "value": r[1]} for r in reversed(rows)]  # 反转 → 时间正序


# ============================================================
# 统计信息
# ============================================================
def get_stats():
    """计算全部历史数据的统计指标。

    返回格式:
        {
          "count": 156,      # 总采集次数
          "avg": 68.25,      # 平均值
          "max": 92.1,       # 最大值
          "min": 41.0        # 最小值
        }
    """
    with get_db(row_factory=False) as conn:
        c = conn.cursor()
        c.execute("SELECT COUNT(*), COALESCE(AVG(value),0), COALESCE(MAX(value),0), COALESCE(MIN(value),0) FROM saturation_history")
        count, avg_val, max_val, min_val = c.fetchone()
    return {
        "count": count,
        "avg": round(avg_val, 2),
        "max": round(max_val, 2),
        "min": round(min_val, 2),
    }


# ============================================================
# 报警日志查询
# ============================================================
def get_alarm_logs(limit=10):
    """查询最近 N 条报警记录。

    返回格式: [{"time": "14:28:01", "value": 85.3, "threshold": 85.0}, ...]
    """
    with get_db(row_factory=False) as conn:
        c = conn.cursor()
        c.execute("SELECT timestamp, value, threshold FROM alarm_log ORDER BY id DESC LIMIT ?", (limit,))
        rows = c.fetchall()
    return [{"time": r[0], "value": r[1], "threshold": r[2]} for r in rows]


# ============================================================
# CSV 导出
# ============================================================
def export_csv_data():
    """导出全部历史数据为 CSV 格式字符串（含表头 id,timestamp,value）。

    编码: UTF-8 BOM，确保 Excel 打开中文不乱码。
    """
    with get_db(row_factory=False) as conn:
        df = pd.read_sql_query("SELECT id, timestamp, value FROM saturation_history ORDER BY id ASC", conn)
    return df.to_csv(index=False)


# ============================================================
# FastAPI 应用生命周期 — 启动时初始化数据库
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    logger.info("正在启动 Saturation Monitor 服务...")
    init_db()               # 建数据表 + 历史/报警表
    init_auth_db()          # 建用户/角色/权限表 + 预置数据
    load_settings_from_db() # 从数据库恢复上次保存的设置（首次则写默认值）
    logger.info("数据库初始化完成，服务已就绪")
    yield
    logger.info("服务已停止")


app = FastAPI(title="Saturation Monitor", lifespan=lifespan)

# 注册认证路由
app.include_router(auth_router)
app.include_router(admin_router)

# 注册鉴权中间件
app.add_middleware(AuthMiddleware)


# ============================================================
# REST API 端点
# ============================================================

@app.get("/api/saturation/current")
def api_current():
    """采集当前饱和度值（从 OneNet 实时获取）。

    返回:
        成功 — {"value": 72.5, "timestamp": "14:30:28", "online": true}
        失败 — {"value": null, "timestamp": "14:30:28", "online": false}

    注意: 每次调用都会写入数据库，相当于一次数据采集。
    """
    value = fetch_from_onenet()
    now = datetime.now().strftime("%H:%M:%S")
    if value is not None:
        save_reading(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), value)
        return {"value": value, "timestamp": now, "online": True}
    return {"value": None, "timestamp": now, "online": False}


@app.get("/api/saturation/history")
def api_history(limit: int = Query(default=50, le=200)):
    """查询最近 N 条历史记录。

    参数: limit — 返回条数，默认 50，最大 200
    示例: /api/saturation/history?limit=20
    """
    return get_history(limit)


@app.get("/api/saturation/stats")
def api_stats():
    """获取全局统计信息（count/avg/max/min）。"""
    return get_stats()


@app.get("/api/alarm/logs")
def api_alarm_logs(limit: int = Query(default=10, le=100)):
    """查询最近 N 条报警日志。

    参数: limit — 返回条数，默认 10，最大 100
    """
    return get_alarm_logs(limit)


@app.get("/api/export/csv")
def api_export_csv():
    """导出全部历史数据为 CSV 文件下载。

    浏览器访问此接口会自动触发下载 "saturation_data.csv"。
    前端点击"导出 CSV"按钮时调用。
    """
    csv_str = export_csv_data()
    return StreamingResponse(
        io.BytesIO(csv_str.encode("utf-8-sig")),       # utf-8-sig = 带 BOM，Excel 兼容
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=saturation_data.csv"}
    )


@app.get("/api/settings")
def api_get_settings():
    """获取当前运行时设置。"""
    return settings


@app.put("/api/settings")
async def api_update_settings(payload: dict):
    """更新运行时设置（前端设置弹窗保存时调用）。

    请求体示例:
        {"refresh_rate": 5, "alarm_threshold": 80}

    refresh_rate    — 范围 1-60 秒
    alarm_threshold — 范围 10-100 %

    修改立即写入数据库，WebSocket 在下次推送时应用新速率。
    """
    if "refresh_rate" in payload:
        settings["refresh_rate"] = max(1, min(60, int(payload["refresh_rate"])))
    if "alarm_threshold" in payload:
        settings["alarm_threshold"] = max(10.0, min(100.0, float(payload["alarm_threshold"])))
    save_settings_to_db()   # 持久化到 SQLite，重启不丢失
    return settings


# ============================================================
# WebSocket 实时推送
# ============================================================
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    """WebSocket 端点 — 通过 Sec-WebSocket-Protocol 头传递 JWT token。

    客户端连接示例:
        new WebSocket("ws://host/ws", ["access_token.<jwt>"])

    使用子协议传递 token 而非 URL 查询参数，避免 token 被记录
    到服务器/代理日志中。
    """
    # 从 Sec-WebSocket-Protocol 头提取 token
    proto_header = ws.headers.get("sec-websocket-protocol", "")
    token = None
    matched_protocol = None
    for proto in proto_header.split(","):
        proto = proto.strip()
        if proto.startswith("access_token."):
            token = proto[len("access_token."):]
            matched_protocol = proto
            break

    if not token:
        await ws.close(code=4001, reason="缺少认证 token")
        return

    try:
        payload = verify_token(token)
        logger.info("WebSocket 客户端已连接 user=%s", payload.get("username"))
    except Exception:
        logger.warning("WebSocket 连接被拒: token 无效")
        await ws.close(code=4001, reason="token 无效或已过期")
        return

    # 接受连接时回传匹配的子协议
    await ws.accept(subprotocol=matched_protocol)
    try:
        while True:
            value = fetch_from_onenet()
            now = datetime.now()
            ts = now.strftime("%Y-%m-%d %H:%M:%S")
            if value is not None:
                # 采集成功：保存 + 判断报警 + 计算统计 + 推送
                save_reading(ts, value)
                alarming = value >= settings["alarm_threshold"]
                stats = get_stats()
                await ws.send_json({
                    "type": "data",
                    "value": value,
                    "timestamp": ts,
                    "alarming": alarming,
                    "stats": stats,
                })
            else:
                # 采集失败：推送错误消息，前端会忽略此条
                await ws.send_json({"type": "error", "message": "数据获取失败"})

            await asyncio.sleep(settings["refresh_rate"])  # 等待指定秒数再下一次
    except WebSocketDisconnect:
        logger.info("WebSocket 客户端已断开 user=%s", payload.get("username"))


# ============================================================
# 静态文件托管 + 启动入口
# ============================================================
# 静态文件托管
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# 根路径 → 登录页
@app.get("/")
def root():
    return FileResponse(os.path.join(STATIC_DIR, "login.html"))

# 仪表板
@app.get("/index.html")
def dashboard():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

if __name__ == "__main__":
    setup_logging()

    # 启动后延时打开浏览器
    def open_browser():
        import time
        time.sleep(1.5)
        webbrowser.open(f"http://localhost:{PORT}")
    threading.Thread(target=open_browser, daemon=True).start()

    logger.info("启动服务 http://%s:%s", HOST, PORT)
    try:
        uvicorn.run(app, host=HOST, port=PORT, log_level="info")
    except Exception as e:
        logger.exception("服务启动失败: %s", e)
        import traceback
        print()
        print("=" * 60)
        print(f"  [FAIL] Server failed to start: {e}")
        print("=" * 60)
        traceback.print_exc()
        print("=" * 60)
        input("Press Enter to exit...")
