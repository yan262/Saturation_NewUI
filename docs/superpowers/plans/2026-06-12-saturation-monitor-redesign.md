# 电缆桥架饱和度监控 UI 重建 — 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Streamlit 仪表板替换为暗色科技风 FastAPI + 纯前端单页应用，实现弧形仪表盘、趋势图、报警日志、CSV 导出等完整监控功能。

**Architecture:** FastAPI 后端代理 OneNet IoT API + SQLite 持久化，通过 REST + WebSocket 向前端提供数据。前端为纯 HTML/CSS/JS 单页，Chart.js 绘图，SVG 自绘弧形仪表盘，Canvas 粒子背景。

**Tech Stack:** Python 3, FastAPI, uvicorn, SQLite3, requests, pandas, HTML5, CSS3, Chart.js 4.x (CDN), Orbitron + JetBrains Mono (Google Fonts CDN)

**Source spec:** `docs/superpowers/specs/2026-06-12-saturation-monitor-redesign.md`

---

## File Structure (Post-Implementation)

```
project_6_1/
├── server.py                  # FastAPI — 新建
├── requirements.txt           # 新建
├── static/
│   ├── index.html             # 新建 — 单页入口
│   ├── css/
│   │   └── style.css          # 新建 — 暗色科技风样式
│   └── js/
│       ├── app.js             # 新建 — 主逻辑 + WebSocket + UI更新
│       ├── gauge.js           # 新建 — 270° SVG 弧形仪表盘
│       └── particles.js       # 新建 — Canvas 背景粒子动画
├── data/                      # 已有目录
│   └── saturation.db          # 已有 — 新增 alarm_log 表
└── dashboard.py               # 已有 — 保留不删
```

---

### Task 1: 项目依赖文件

**Files:**
- Create: `e:/test/project/project_6_1/requirements.txt`

- [ ] **Step 1: 写入 requirements.txt**

```text
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
requests>=2.31.0
pandas>=2.2.0
```

- [ ] **Step 2: 安装依赖**

```bash
pip install -r e:/test/project/project_6_1/requirements.txt
```

---

### Task 2: FastAPI 后端 — 核心框架 + OneNet 数据采集 + SQLite

**Files:**
- Create: `e:/test/project/project_6_1/server.py`

- [ ] **Step 1: 创建 server.py 骨架与配置常量**

```python
"""
电缆桥架饱和度监控 — FastAPI 后端
===================================
提供 REST API + WebSocket，代理 OneNet IoT 平台数据采集，
SQLite 本地持久化历史记录和报警日志。
"""
import asyncio
import sqlite3
import os
import csv
import io
from datetime import datetime
from contextlib import asynccontextmanager

import requests
import pandas as pd
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

# ================= OneNet 配置 =================
PRODUCT_ID = "IqV8M48sQQ"
DEVICE_NAME = "Saturation_Detection"
TOKEN = "version=2018-10-31&res=products%2FIqV8M48sQQ%2Fdevices%2FSaturation_Detection&et=2058447118&method=md5&sign=rzM7OnlFyCMOexl5ixFGYQ%3D%3D"
API_URL = "https://iot-api.heclouds.com/thingmodel/query-device-property"

# ================= SQLite 路径 =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "data", "saturation.db")
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)

# ================= 运行时设置（内存中） =================
settings = {
    "refresh_rate": 2,
    "alarm_threshold": 85.0,
}
```

- [ ] **Step 2: 添加数据库初始化函数**

```python
def init_db():
    """创建 saturation_history 和 alarm_log 两张表（如不存在）。"""
    conn = sqlite3.connect(DB_PATH)
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
    conn.commit()
    conn.close()
```

- [ ] **Step 3: 添加 OneNet 数据采集函数**

```python
def fetch_from_onenet():
    """调用 OneNet 物模型接口，读取 Saturation 属性值。成功返回 float，失败返回 None。"""
    headers = {"Authorization": TOKEN}
    params = {"product_id": PRODUCT_ID, "device_name": DEVICE_NAME}
    try:
        resp = requests.get(API_URL, headers=headers, params=params, timeout=10)
        data = resp.json()
        if data.get("code") == 0:
            for prop in data.get("data", []):
                if prop.get("identifier") == "Saturation":
                    return float(prop.get("value", 0.0))
    except Exception:
        pass
    return None
```

- [ ] **Step 4: 添加存储与统计查询函数**

```python
def save_reading(timestamp_str, value):
    """保存一条饱和度读数；若超阈值则同时写入报警日志。"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("INSERT INTO saturation_history (timestamp, value) VALUES (?, ?)",
              (timestamp_str, value))
    if value >= settings["alarm_threshold"]:
        c.execute("INSERT INTO alarm_log (timestamp, value, threshold) VALUES (?, ?, ?)",
                  (timestamp_str, value, settings["alarm_threshold"]))
    conn.commit()
    conn.close()


def get_history(limit=50):
    """查询最近 N 条历史记录，按时间正序返回。"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT timestamp, value FROM saturation_history ORDER BY id DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return [{"time": r[0], "value": r[1]} for r in reversed(rows)]


def get_stats():
    """返回饱和度统计信息。"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT COUNT(*), COALESCE(AVG(value),0), COALESCE(MAX(value),0), COALESCE(MIN(value),0) FROM saturation_history")
    count, avg_val, max_val, min_val = c.fetchone()
    conn.close()
    return {"count": count, "avg": round(avg_val, 2), "max": round(max_val, 2), "min": round(min_val, 2)}


def get_alarm_logs(limit=10):
    """查询最近 N 条报警记录。"""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("SELECT timestamp, value, threshold FROM alarm_log ORDER BY id DESC LIMIT ?", (limit,))
    rows = c.fetchall()
    conn.close()
    return [{"time": r[0], "value": r[1], "threshold": r[2]} for r in rows]


def export_csv_data():
    """导出全部历史数据为 CSV 字符串。"""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT id, timestamp, value FROM saturation_history ORDER BY id ASC", conn)
    conn.close()
    return df.to_csv(index=False)
```

- [ ] **Step 5: 创建 FastAPI app + 生命周期**

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="Saturation Monitor", lifespan=lifespan)
```

- [ ] **Step 6: 添加 REST 端点**

```python
@app.get("/api/saturation/current")
def api_current():
    value = fetch_from_onenet()
    now = datetime.now().strftime("%H:%M:%S")
    if value is not None:
        save_reading(datetime.now().strftime("%Y-%m-%d %H:%M:%S"), value)
        return {"value": value, "timestamp": now, "online": True}
    return {"value": None, "timestamp": now, "online": False}


@app.get("/api/saturation/history")
def api_history(limit: int = Query(default=50, le=200)):
    return get_history(limit)


@app.get("/api/saturation/stats")
def api_stats():
    return get_stats()


@app.get("/api/alarm/logs")
def api_alarm_logs(limit: int = Query(default=10, le=100)):
    return get_alarm_logs(limit)


@app.get("/api/export/csv")
def api_export_csv():
    csv_str = export_csv_data()
    return StreamingResponse(
        io.BytesIO(csv_str.encode("utf-8-sig")),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=saturation_data.csv"}
    )


@app.get("/api/settings")
def api_get_settings():
    return settings


@app.put("/api/settings")
async def api_update_settings(payload: dict):
    if "refresh_rate" in payload:
        settings["refresh_rate"] = max(1, min(60, int(payload["refresh_rate"])))
    if "alarm_threshold" in payload:
        settings["alarm_threshold"] = max(10.0, min(100.0, float(payload["alarm_threshold"])))
    return settings
```

- [ ] **Step 7: 添加 WebSocket 端点**

```python
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            value = fetch_from_onenet()
            now = datetime.now()
            ts = now.strftime("%Y-%m-%d %H:%M:%S")
            if value is not None:
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
                await ws.send_json({"type": "error", "message": "数据获取失败"})
            await asyncio.sleep(settings["refresh_rate"])
    except WebSocketDisconnect:
        pass
```

- [ ] **Step 8: 挂载静态文件 + 启动入口**

```python
app.mount("/", StaticFiles(directory=os.path.join(BASE_DIR, "static"), html=True), name="static")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

- [ ] **Step 9: 验证后端可启动**

```bash
cd e:/test/project/project_6_1 && timeout 5 python server.py 2>&1 || true
```

Expected: 看到 uvicorn 启动日志，端口 8000。

---

### Task 3: 前端 HTML 页面结构

**Files:**
- Create: `e:/test/project/project_6_1/static/index.html`

- [ ] **Step 1: 创建 index.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>电缆桥架饱和度监控</title>
    <!-- Google Fonts: Orbitron (科技感) + JetBrains Mono (日志等宽) -->
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
    <link href="https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <!-- Chart.js -->
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <link rel="stylesheet" href="/css/style.css">
</head>
<body>
    <!-- 背景粒子 canvas -->
    <canvas id="particles-canvas"></canvas>

    <!-- 页面顶部报警呼吸光条 -->
    <div id="alarm-glow-bar"></div>

    <!-- 页眉 -->
    <header id="header">
        <div class="header-left">
            <span class="header-icon">⚡</span>
            <h1 class="header-title">电缆桥架饱和度监控平台</h1>
            <span id="online-badge" class="badge badge-warn">◉ 检测中...</span>
        </div>
        <div class="header-right">
            <span class="header-info" id="clock">--:--:--</span>
            <span id="ws-badge" class="badge badge-warn">⬡ 连接中...</span>
        </div>
    </header>

    <!-- 主区域：仪表盘 | 实时值 | 趋势图 -->
    <main id="main-row">
        <!-- 左侧：弧形仪表盘 -->
        <section id="gauge-section">
            <div id="gauge-container"></div>
        </section>

        <!-- 中间：实时值卡片 -->
        <section id="value-section">
            <div class="glass-card" id="current-value-card">
                <div class="card-label">📊 实时饱和度</div>
                <div class="card-big-value" id="current-value">--.-</div>
                <div class="card-unit">%</div>
                <div class="card-delta" id="delta-text">等待采集...</div>
            </div>
        </section>

        <!-- 右侧：趋势面积图 -->
        <section id="chart-section">
            <div class="glass-card chart-card">
                <div class="card-label">📈 饱和度趋势</div>
                <canvas id="trend-chart"></canvas>
            </div>
        </section>
    </main>

    <!-- 进度条行 -->
    <section id="progress-section">
        <div class="glass-card" id="progress-card">
            <div class="card-label">📏 阈值占用率（报警阈值: <span id="threshold-label">85</span>%）</div>
            <div class="progress-track">
                <div class="progress-fill" id="progress-fill"></div>
            </div>
            <div class="progress-labels">
                <span>0%</span>
                <span id="progress-text">--.-% / --%</span>
                <span>100%</span>
            </div>
        </div>
    </section>

    <!-- 统计行 -->
    <section id="stats-section">
        <div class="glass-card stat-card">
            <div class="card-label">📈 平均值</div>
            <div class="stat-value" id="stat-avg">--.-<small>%</small></div>
        </div>
        <div class="glass-card stat-card">
            <div class="card-label">🔺 最大值</div>
            <div class="stat-value text-red" id="stat-max">--.-<small>%</small></div>
            <div class="stat-time" id="stat-max-time"></div>
        </div>
        <div class="glass-card stat-card">
            <div class="card-label">🔽 最小值</div>
            <div class="stat-value text-green" id="stat-min">--.-<small>%</small></div>
            <div class="stat-time" id="stat-min-time"></div>
        </div>
        <div class="glass-card stat-card">
            <div class="card-label">📋 采样次数</div>
            <div class="stat-value" id="stat-count">0</div>
        </div>
    </section>

    <!-- 报警日志 + 操作按钮 -->
    <section id="log-section">
        <div class="glass-card log-card">
            <div class="log-header">
                <span class="card-label">⚠ 报警日志（最近5条）</span>
                <div class="log-actions">
                    <button class="btn-glass" id="btn-export">📥 导出 CSV</button>
                    <button class="btn-glass" id="btn-settings">⚙ 设置</button>
                </div>
            </div>
            <div id="log-list">
                <div class="log-empty">暂无报警记录</div>
            </div>
        </div>
    </section>

    <!-- 底栏 -->
    <footer id="footer">
        <span>🔄 刷新: <strong id="footer-rate">2</strong>s</span>
        <span>🚨 阈值: <strong id="footer-threshold">85</strong>%</span>
        <span class="footer-tech">FastAPI + OneNet 云平台</span>
    </footer>

    <!-- 设置弹窗 -->
    <div id="settings-overlay" class="overlay hidden">
        <div class="glass-card settings-dialog">
            <h2>⚙ 监控设置</h2>
            <div class="setting-row">
                <label>🔄 刷新频率（秒）</label>
                <input type="range" id="setting-rate" min="1" max="30" value="2">
                <span id="setting-rate-val">2</span>
            </div>
            <div class="setting-row">
                <label>🚨 报警阈值（%）</label>
                <input type="range" id="setting-threshold" min="10" max="100" value="85">
                <span id="setting-threshold-val">85</span>
            </div>
            <div class="setting-actions">
                <button class="btn-glass" id="btn-save-settings">保存</button>
                <button class="btn-glass" id="btn-close-settings">取消</button>
            </div>
        </div>
    </div>

    <!-- JS -->
    <script src="/js/gauge.js"></script>
    <script src="/js/particles.js"></script>
    <script src="/js/app.js"></script>
</body>
</html>
```

---

### Task 4: CSS 暗色科技风样式

**Files:**
- Create: `e:/test/project/project_6_1/static/css/style.css`

- [ ] **Step 1: 创建 CSS Reset + 基础变量 + 背景**

```css
/* ===== CSS Variables ===== */
:root {
    --bg-deep: #060b14;
    --card-bg: rgba(10, 25, 50, 0.6);
    --card-border: rgba(30, 60, 100, 0.5);
    --cyan: #00e5ff;
    --green: #00ff88;
    --yellow: #ffaa00;
    --red: #ff3333;
    --text-primary: #e0e8f0;
    --text-secondary: #5a7a9a;
    --glow-cyan: 0 0 20px rgba(0, 229, 255, 0.3);
    --glow-red: 0 0 30px rgba(255, 51, 51, 0.5);
    --font-mono: 'JetBrains Mono', monospace;
    --font-display: 'Orbitron', monospace;
}

/* ===== Reset ===== */
*, *::before, *::after { margin: 0; padding: 0; box-sizing: border-box; }

html, body {
    height: 100vh;
    overflow: hidden;
    background: var(--bg-deep);
    color: var(--text-primary);
    font-family: system-ui, -apple-system, sans-serif;
    font-size: 15px;
}

/* ===== Particle Canvas ===== */
#particles-canvas {
    position: fixed;
    top: 0; left: 0;
    width: 100%; height: 100%;
    z-index: 0;
    pointer-events: none;
}

/* ===== Alarm Glow Bar ===== */
#alarm-glow-bar {
    position: fixed; top: 0; left: 0;
    width: 100%; height: 3px;
    background: transparent;
    z-index: 1000;
    transition: background 0.3s, box-shadow 0.3s;
}
#alarm-glow-bar.active {
    background: var(--red);
    box-shadow: 0 0 20px var(--red), 0 0 60px rgba(255, 51, 51, 0.6);
    animation: alarm-pulse 1.5s ease-in-out infinite;
}

@keyframes alarm-pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
}
```

- [ ] **Step 2: 创建页眉样式**

```css
/* ===== Header ===== */
#header {
    position: relative; z-index: 1;
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 10px 24px 8px;
    border-bottom: 1px solid var(--card-border);
    margin-bottom: 8px;
}
.header-left, .header-right {
    display: flex;
    align-items: center;
    gap: 14px;
}
.header-icon { font-size: 30px; }
.header-title {
    font-size: 22px;
    font-weight: 700;
    color: var(--text-primary);
}
.header-info {
    font-size: 14px;
    color: var(--text-secondary);
}

/* ===== Badge ===== */
.badge {
    display: inline-block;
    padding: 3px 12px;
    border-radius: 10px;
    font-size: 12px;
    font-weight: 600;
    font-family: var(--font-mono);
}
.badge-normal {
    background: rgba(0, 255, 136, 0.15);
    color: var(--green);
    border: 1px solid rgba(0, 255, 136, 0.3);
}
.badge-warn {
    background: rgba(255, 170, 0, 0.15);
    color: var(--yellow);
    border: 1px solid rgba(255, 170, 0, 0.3);
}
.badge-danger {
    background: rgba(255, 51, 51, 0.15);
    color: var(--red);
    border: 1px solid rgba(255, 51, 51, 0.3);
}
```

- [ ] **Step 3: 创建玻璃卡片 + 主区域布局**

```css
/* ===== Glass Card ===== */
.glass-card {
    background: var(--card-bg);
    border: 1px solid var(--card-border);
    border-radius: 12px;
    padding: 14px 18px;
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
}
.card-label {
    font-size: 12px;
    text-transform: uppercase;
    letter-spacing: 1.5px;
    color: var(--text-secondary);
    margin-bottom: 6px;
}

/* ===== Main Row ===== */
#main-row {
    position: relative; z-index: 1;
    display: flex;
    gap: 12px;
    padding: 0 24px;
    height: 340px;
}
#gauge-section {
    flex: 0 0 300px;
    display: flex;
    align-items: center;
    justify-content: center;
}
#value-section {
    flex: 0 0 220px;
    display: flex;
    align-items: center;
}
#chart-section {
    flex: 1;
    min-width: 0;
}
.chart-card {
    height: 100%;
    display: flex;
    flex-direction: column;
}
.chart-card canvas {
    flex: 1;
    max-height: 280px;
}
```

- [ ] **Step 4: 创建实时值卡片样式**

```css
/* ===== Current Value Card ===== */
#current-value-card {
    width: 100%;
    text-align: center;
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    height: 100%;
}
.card-big-value {
    font-family: var(--font-display);
    font-size: 56px;
    font-weight: 900;
    color: var(--cyan);
    text-shadow: var(--glow-cyan);
    line-height: 1.1;
    transition: color 0.5s;
}
.card-big-value.alarming {
    color: var(--red);
    text-shadow: var(--glow-red);
}
.card-unit {
    font-family: var(--font-display);
    font-size: 20px;
    color: var(--text-secondary);
    margin-top: -2px;
}
.card-delta {
    font-size: 13px;
    font-family: var(--font-mono);
    margin-top: 8px;
    color: var(--text-secondary);
}
.card-delta.up { color: var(--red); }
.card-delta.down { color: var(--green); }
```

- [ ] **Step 5: 创建进度条样式**

```css
/* ===== Progress Section ===== */
#progress-section {
    position: relative; z-index: 1;
    padding: 0 24px;
    margin-top: 10px;
}
.progress-track {
    height: 24px;
    background: rgba(20, 40, 70, 0.8);
    border-radius: 12px;
    overflow: hidden;
    border: 1px solid var(--card-border);
}
.progress-fill {
    height: 100%;
    width: 0%;
    border-radius: 12px;
    background: linear-gradient(90deg, var(--green), var(--yellow));
    transition: width 0.6s ease, background 0.6s;
    box-shadow: 0 0 12px rgba(0, 229, 255, 0.2);
}
.progress-fill.warning {
    background: linear-gradient(90deg, var(--yellow), var(--red));
    box-shadow: 0 0 16px rgba(255, 51, 51, 0.4);
}
.progress-labels {
    display: flex;
    justify-content: space-between;
    margin-top: 4px;
    font-size: 12px;
    color: var(--text-secondary);
    font-family: var(--font-mono);
}
```

- [ ] **Step 6: 创建统计卡片样式**

```css
/* ===== Stats Section ===== */
#stats-section {
    position: relative; z-index: 1;
    display: flex;
    gap: 10px;
    padding: 0 24px;
    margin-top: 10px;
}
.stat-card {
    flex: 1;
    text-align: center;
}
.stat-value {
    font-family: var(--font-display);
    font-size: 30px;
    font-weight: 700;
    color: var(--cyan);
}
.stat-value small {
    font-size: 16px;
    color: var(--text-secondary);
    margin-left: 2px;
}
.stat-value.text-red { color: var(--red); }
.stat-value.text-green { color: var(--green); }
.stat-time {
    font-size: 11px;
    color: var(--text-secondary);
    font-family: var(--font-mono);
    margin-top: 2px;
}
```

- [ ] **Step 7: 创建报警日志样式**

```css
/* ===== Log Section ===== */
#log-section {
    position: relative; z-index: 1;
    padding: 0 24px;
    margin-top: 10px;
}
.log-card { min-height: 130px; }
.log-header {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-bottom: 8px;
}
.log-actions { display: flex; gap: 8px; }
.btn-glass {
    background: rgba(0, 229, 255, 0.1);
    border: 1px solid rgba(0, 229, 255, 0.3);
    color: var(--cyan);
    padding: 6px 14px;
    border-radius: 6px;
    cursor: pointer;
    font-size: 13px;
    font-family: inherit;
    transition: all 0.2s;
}
.btn-glass:hover {
    background: rgba(0, 229, 255, 0.2);
    box-shadow: var(--glow-cyan);
}
#log-list {
    display: flex;
    flex-wrap: wrap;
    gap: 8px;
}
.log-entry {
    font-family: var(--font-mono);
    font-size: 12px;
    padding: 4px 10px;
    border-radius: 6px;
    background: rgba(255, 51, 51, 0.08);
    border: 1px solid rgba(255, 51, 51, 0.2);
    color: var(--text-primary);
    white-space: nowrap;
}
.log-entry .time { color: var(--text-secondary); }
.log-entry .val { font-weight: 600; }
.log-entry.alarm-high { border-color: rgba(255, 51, 51, 0.5); }
.log-entry.alarm-high .val { color: var(--red); }
.log-empty {
    color: var(--text-secondary);
    font-size: 13px;
    padding: 10px 0;
}
```

- [ ] **Step 8: 创建底栏 + 设置弹窗样式**

```css
/* ===== Footer ===== */
#footer {
    position: fixed; bottom: 0; left: 0;
    width: 100%; z-index: 10;
    display: flex;
    justify-content: center;
    gap: 24px;
    padding: 6px 24px;
    background: rgba(6, 11, 20, 0.9);
    border-top: 1px solid var(--card-border);
    font-size: 13px;
    color: var(--text-secondary);
}
#footer strong { color: var(--text-primary); font-family: var(--font-mono); }
.footer-tech { color: var(--text-secondary); }

/* ===== Settings Overlay ===== */
.overlay {
    position: fixed;
    top: 0; left: 0;
    width: 100%; height: 100%;
    background: rgba(0,0,0,0.7);
    z-index: 999;
    display: flex;
    align-items: center;
    justify-content: center;
}
.overlay.hidden { display: none; }
.settings-dialog {
    width: 380px;
    padding: 24px;
}
.settings-dialog h2 {
    font-size: 18px;
    margin-bottom: 16px;
    color: var(--text-primary);
}
.setting-row {
    display: flex;
    align-items: center;
    gap: 12px;
    margin-bottom: 12px;
}
.setting-row label { flex: 1; font-size: 14px; color: var(--text-secondary); }
.setting-row input[type="range"] { flex: 2; accent-color: var(--cyan); }
.setting-row span {
    font-family: var(--font-mono);
    color: var(--cyan);
    min-width: 30px;
    text-align: right;
}
.setting-actions {
    display: flex;
    gap: 10px;
    margin-top: 20px;
    justify-content: flex-end;
}
```

---

### Task 5: JavaScript — 弧形仪表盘 (gauge.js)

**Files:**
- Create: `e:/test/project/project_6_1/static/js/gauge.js`

- [ ] **Step 1: 创建 gauge.js — 270° SVG 弧形仪表盘**

```javascript
/**
 * 270° SVG 弧形仪表盘
 * 用法: GaugeRenderer.render(container, value, threshold, alarming)
 */
const GaugeRenderer = {
  render(container, value, threshold, alarming) {
    const cx = 150, cy = 160;
    const trackR = 110, trackW = 18;
    const viewW = 300, viewH = 260;

    // 将百分比值映射到角度: 0% = 左侧225°, 100% = 右侧315°
    const startAngle = 225, totalArc = 270;

    // 极坐标转 SVG 直角坐标
    function pt(angleDeg, dist) {
      const rad = (angleDeg * Math.PI) / 180;
      return {
        x: cx + dist * Math.cos(rad),
        y: cy + dist * Math.sin(rad),
      };
    }

    // 弧形端点
    const leftPt = pt(startAngle, trackR);
    const rightPt = pt(startAngle + totalArc, trackR);

    // 色区比例（基于阈值）
    const safeRatio = Math.min((threshold * 0.8) / 100, 1.0);
    const warnRatio = Math.min(threshold / 100, 1.0);
    const greenEnd = pt(startAngle + safeRatio * totalArc, trackR);
    const yellowEnd = pt(startAngle + warnRatio * totalArc, trackR);

    // 指针
    const valRatio = Math.min(Math.max(value / 100, 0), 1);
    const needleAngle = startAngle + valRatio * totalArc;
    const needleBase = pt(needleAngle, trackR - 60);
    const needleTip = pt(needleAngle, trackR - 8);
    const isAlarming = value >= threshold;
    const needleColor = isAlarming ? '#ff3333' : value < threshold * 0.8 ? '#00ff88' : '#ffaa00';

    // 刻度线
    let ticksMarkup = '';
    for (let pct = 0; pct <= 100; pct += 20) {
      const a = startAngle + (pct / 100) * totalArc;
      const p1 = pt(a, trackR + 8);
      const p2 = pt(a, trackR + 22);
      const lb = pt(a, trackR + 42);
      ticksMarkup += `
        <line x1="${p1.x.toFixed(1)}" y1="${p1.y.toFixed(1)}" x2="${p2.x.toFixed(1)}" y2="${p2.y.toFixed(1)}"
              stroke="#3a5a7a" stroke-width="1.5"/>
        <text x="${lb.x.toFixed(1)}" y="${lb.y.toFixed(1)}" text-anchor="middle"
              fill="#5a7a9a" font-size="11" font-family="'JetBrains Mono', monospace">${pct}</text>`;
    }

    const svg = `
    <svg width="100%" viewBox="0 0 ${viewW} ${viewH}" style="max-width:340px;">
      <defs>
        <filter id="glow-green"><feGaussianBlur stdDeviation="3" result="blur"/>
          <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        <filter id="glow-red"><feGaussianBlur stdDeviation="4" result="blur"/>
          <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
        <filter id="glow-needle"><feGaussianBlur stdDeviation="2" result="blur"/>
          <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
      </defs>

      <!-- 灰色底轨 -->
      <path d="M${leftPt.x.toFixed(1)} ${leftPt.y.toFixed(1)}
               A${trackR} ${trackR} 0 0 1 ${rightPt.x.toFixed(1)} ${rightPt.y.toFixed(1)}"
            fill="none" stroke="#1a2a40" stroke-width="${trackW}" stroke-linecap="round"/>

      <!-- 绿色安全区 -->
      <path d="M${leftPt.x.toFixed(1)} ${leftPt.y.toFixed(1)}
               A${trackR} ${trackR} 0 0 1 ${greenEnd.x.toFixed(1)} ${greenEnd.y.toFixed(1)}"
            fill="none" stroke="#00ff88" stroke-width="${trackW - 4}" stroke-linecap="butt"
            filter="url(#glow-green)" opacity="0.9"/>

      <!-- 黄色警告区 -->
      <path d="M${greenEnd.x.toFixed(1)} ${greenEnd.y.toFixed(1)}
               A${trackR} ${trackR} 0 0 1 ${yellowEnd.x.toFixed(1)} ${yellowEnd.y.toFixed(1)}"
            fill="none" stroke="#ffaa00" stroke-width="${trackW - 4}" stroke-linecap="butt" opacity="0.9"/>

      <!-- 红色危险区 -->
      <path d="M${yellowEnd.x.toFixed(1)} ${yellowEnd.y.toFixed(1)}
               A${trackR} ${trackR} 0 0 1 ${rightPt.x.toFixed(1)} ${rightPt.y.toFixed(1)}"
            fill="none" stroke="#ff3333" stroke-width="${trackW - 4}" stroke-linecap="butt"
            filter="url(#glow-red)" opacity="0.9"/>

      ${ticksMarkup}

      <!-- 指针 -->
      <line x1="${needleBase.x.toFixed(1)}" y1="${needleBase.y.toFixed(1)}"
            x2="${needleTip.x.toFixed(1)}" y2="${needleTip.y.toFixed(1)}"
            stroke="${needleColor}" stroke-width="3" stroke-linecap="round"
            filter="url(#glow-needle)" style="transition: all 0.5s ease;"/>

      <!-- 圆心 -->
      <circle cx="${cx}" cy="${cy}" r="10" fill="#060b14"
              stroke="${needleColor}" stroke-width="3" filter="url(#glow-needle)"/>

      <!-- 中心数值 -->
      <text x="${cx}" y="${cy - 38}" text-anchor="middle"
            fill="${isAlarming ? '#ff3333' : '#00e5ff'}"
            font-size="46" font-weight="900" font-family="'Orbitron', monospace"
            filter="${isAlarming ? 'url(#glow-red)' : ''}">${value.toFixed(1)}%</text>

      <!-- 中心下方标签 -->
      <text x="${cx}" y="${cy + 22}" text-anchor="middle"
            fill="#5a7a9a" font-size="13" font-family="'Orbitron', monospace"
            letter-spacing="4">饱和度</text>
    </svg>`;

    container.innerHTML = svg;
  },
};
```

---

### Task 6: JavaScript — 背景粒子动画 (particles.js)

**Files:**
- Create: `e:/test/project/project_6_1/static/js/particles.js`

- [ ] **Step 1: 创建 particles.js — Canvas 粒子背景**

```javascript
/**
 * 背景粒子动画 — 缓慢飘动的微小光点，营造科技感氛围。
 */
const Particles = {
  _particles: [],
  _canvas: null,
  _ctx: null,
  _animId: null,

  init(canvasId) {
    this._canvas = document.getElementById(canvasId);
    this._ctx = this._canvas.getContext('2d');
    this._resize();
    window.addEventListener('resize', () => this._resize());

    const count = 50;
    for (let i = 0; i < count; i++) {
      this._particles.push({
        x: Math.random() * this._canvas.width,
        y: Math.random() * this._canvas.height,
        r: Math.random() * 1.5 + 0.5,
        vx: (Math.random() - 0.5) * 0.3,
        vy: (Math.random() - 0.5) * 0.3,
        alpha: Math.random() * 0.4 + 0.1,
      });
    }
    this._animate();
  },

  _resize() {
    this._canvas.width = window.innerWidth;
    this._canvas.height = window.innerHeight;
  },

  _animate() {
    this._ctx.clearRect(0, 0, this._canvas.width, this._canvas.height);

    for (const p of this._particles) {
      p.x += p.vx;
      p.y += p.vy;

      // 边框回弹
      if (p.x < 0 || p.x > this._canvas.width) p.vx *= -1;
      if (p.y < 0 || p.y > this._canvas.height) p.vy *= -1;

      this._ctx.beginPath();
      this._ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
      this._ctx.fillStyle = `rgba(0, 229, 255, ${p.alpha})`;
      this._ctx.fill();
    }

    // 粒子间连线
    this._ctx.strokeStyle = 'rgba(0, 229, 255, 0.04)';
    this._ctx.lineWidth = 0.5;
    for (let i = 0; i < this._particles.length; i++) {
      for (let j = i + 1; j < this._particles.length; j++) {
        const a = this._particles[i], b = this._particles[j];
        const dx = a.x - b.x, dy = a.y - b.y;
        const dist = Math.sqrt(dx * dx + dy * dy);
        if (dist < 120) {
          this._ctx.beginPath();
          this._ctx.moveTo(a.x, a.y);
          this._ctx.lineTo(b.x, b.y);
          this._ctx.stroke();
        }
      }
    }

    this._animId = requestAnimationFrame(() => this._animate());
  },
};
```

---

### Task 7: JavaScript — 主应用逻辑 (app.js)

**Files:**
- Create: `e:/test/project/project_6_1/static/js/app.js`

- [ ] **Step 1: 创建 app.js 前半 — 状态管理 + 图表 + 时间**

```javascript
/**
 * 电缆桥架饱和度监控 — 主应用逻辑
 * 职责: WebSocket 连接、Chart.js 图表、UI 更新、设置管理、CSV 导出
 */
(function () {
  'use strict';

  // ===== 内部状态 =====
  const state = {
    history: [],        // [{ time, value }, ...] 最多 50 条
    prevValue: null,    // 上一次采集值
    alarmCount: 0,
    alarmMinutes: 0,
    alarming: false,
    settings: { refresh_rate: 2, alarm_threshold: 85 },
    ws: null,
    chart: null,
    chartInitialized: false,
  };

  // ===== DOM 引用 =====
  const $ = (sel) => document.querySelector(sel);

  // ===== Chart.js 初始化 =====
  function initChart() {
    const ctx = $('#trend-chart').getContext('2d');
    state.chart = new Chart(ctx, {
      type: 'line',
      data: { labels: [], datasets: [{
        label: '饱和度',
        data: [],
        borderColor: '#00e5ff',
        backgroundColor: 'rgba(0, 229, 255, 0.10)',
        fill: true,
        borderWidth: 2,
        pointRadius: 0,
        tension: 0.3,
      }] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        animation: { duration: 400 },
        plugins: { legend: { display: false } },
        scales: {
          x: {
            ticks: { color: '#5a7a9a', font: { size: 11, family: "'JetBrains Mono', monospace" }, maxTicksLimit: 8 },
            grid: { color: 'rgba(30, 60, 100, 0.3)' },
          },
          y: {
            min: 0, max: 100,
            ticks: { color: '#5a7a9a', font: { size: 11, family: "'JetBrains Mono', monospace" }, stepSize: 20,
              callback: (v) => v + '%' },
            grid: { color: 'rgba(30, 60, 100, 0.3)' },
          },
        },
      },
    });
    state.chartInitialized = true;
  }
```

- [ ] **Step 2: 创建 app.js 中间 — 时钟 + UI 更新函数**

```javascript
  // ===== 时钟更新 =====
  function updateClock() {
    const now = new Date();
    $('#clock').textContent = now.toLocaleTimeString('zh-CN', { hour12: false });
  }
  setInterval(updateClock, 1000);
  updateClock();

  // ===== 仪表盘更新 =====
  function updateGauge(value, threshold, alarming) {
    GaugeRenderer.render($('#gauge-container'), value, threshold, alarming);
  }

  // ===== 实时值卡片更新 =====
  function updateValueCard(value, prevValue) {
    const el = $('#current-value');
    el.textContent = value.toFixed(1);
    const threshold = state.settings.alarm_threshold;
    el.classList.toggle('alarming', value >= threshold);

    const deltaEl = $('#delta-text');
    if (prevValue !== null) {
      const diff = value - prevValue;
      deltaEl.textContent = diff > 0 ? `▲ 较上次 +${diff.toFixed(1)}%` : `▼ 较上次 ${diff.toFixed(1)}%`;
      deltaEl.className = 'card-delta ' + (diff > 0 ? 'up' : 'down');
    } else {
      deltaEl.textContent = '首次采集';
      deltaEl.className = 'card-delta';
    }
  }

  // ===== 趋势图更新 =====
  function updateChart(history) {
    if (!state.chartInitialized) initChart();
    state.chart.data.labels = history.map(h => h.time);
    state.chart.data.datasets[0].data = history.map(h => h.value);
    state.chart.update('none');
  }

  // ===== 进度条更新 =====
  function updateProgress(value, threshold) {
    const pct = Math.min((value / threshold) * 100, 100);
    const fill = $('#progress-fill');
    fill.style.width = pct + '%';
    fill.classList.toggle('warning', pct >= 90 || value >= threshold);
    $('#progress-text').textContent = `${value.toFixed(1)}% / ${threshold}%`;
  }

  // ===== 统计卡片更新 =====
  function updateStats(stats) {
    $('#stat-avg').innerHTML = `${stats.avg.toFixed(1)}<small>%</small>`;
    $('#stat-max').innerHTML = `${stats.max.toFixed(1)}<small>%</small>`;
    $('#stat-min').innerHTML = `${stats.min.toFixed(1)}<small>%</small>`;
    $('#stat-count').textContent = stats.count;
  }

  // ===== 报警日志更新 =====
  function addAlarmLog(entry) {
    const list = $('#log-list');
    // 移除空状态提示
    const empty = list.querySelector('.log-empty');
    if (empty) empty.remove();

    const div = document.createElement('div');
    div.className = 'log-entry alarm-high';
    const timeShort = entry.time.slice(-8);
    div.innerHTML = `<span class="time">${timeShort}</span> <span class="val">${entry.value.toFixed(1)}%</span> 🔴 超阈值`;
    list.insertBefore(div, list.firstChild);

    // 只保留最近 5 条
    while (list.children.length > 5) list.removeChild(list.lastChild);
  }

  // ===== 报警呼吸条 =====
  function updateAlarmState(alarming) {
    const bar = $('#alarm-glow-bar');
    bar.classList.toggle('active', alarming);
  }

  // ===== 状态徽章 =====
  function updateBadges(online) {
    const badge = $('#online-badge');
    const wsBadge = $('#ws-badge');
    if (online) {
      badge.className = 'badge badge-normal';
      badge.textContent = '● 在线';
      wsBadge.className = 'badge badge-normal';
      wsBadge.textContent = '⬡ WebSocket';
    } else {
      badge.className = 'badge badge-danger';
      badge.textContent = '● 离线';
      wsBadge.className = 'badge badge-danger';
      wsBadge.textContent = '⬡ 断开';
    }
  }
```

- [ ] **Step 3: 创建 app.js 后半 — WebSocket + 设置 + 导出 + 初始化**

```javascript
  // ===== WebSocket 连接 =====
  function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws`;

    function connect() {
      state.ws = new WebSocket(wsUrl);
      state.ws.onopen = () => updateBadges(true);
      state.ws.onmessage = (event) => {
        const msg = JSON.parse(event.data);
        if (msg.type === 'data') {
          handleData(msg);
        }
      };
      state.ws.onclose = () => {
        updateBadges(false);
        setTimeout(connect, 3000);
      };
      state.ws.onerror = () => state.ws.close();
    }
    connect();
  }

  // ===== 数据处理 =====
  function handleData(msg) {
    const { value, timestamp, alarming, stats } = msg;
    const threshold = state.settings.alarm_threshold;

    // 更新历史
    const timeShort = timestamp.slice(-8);
    state.history.push({ time: timeShort, value });
    if (state.history.length > 50) state.history.shift();

    // 更新所有 UI
    updateGauge(value, threshold, alarming);
    updateValueCard(value, state.prevValue);
    updateChart(state.history);
    updateProgress(value, threshold);
    updateStats(stats);
    updateAlarmState(alarming);

    // 报警日志
    if (alarming) {
      addAlarmLog({ time: timestamp, value });
    }

    // 累计
    if (alarming && !state.alarming) state.alarmCount++;
    state.alarming = alarming;
    state.prevValue = value;
  }

  // ===== 设置面板 =====
  function initSettings() {
    $('#btn-settings').addEventListener('click', () => {
      $('#settings-overlay').classList.remove('hidden');
      $('#setting-rate').value = state.settings.refresh_rate;
      $('#setting-threshold').value = state.settings.alarm_threshold;
      $('#setting-rate-val').textContent = state.settings.refresh_rate;
      $('#setting-threshold-val').textContent = state.settings.alarm_threshold;
    });

    $('#btn-close-settings').addEventListener('click', () => {
      $('#settings-overlay').classList.add('hidden');
    });

    $('#setting-rate').addEventListener('input', function () {
      $('#setting-rate-val').textContent = this.value;
    });
    $('#setting-threshold').addEventListener('input', function () {
      $('#setting-threshold-val').textContent = this.value;
    });

    $('#btn-save-settings').addEventListener('click', async () => {
      const rate = parseInt($('#setting-rate').value);
      const threshold = parseFloat($('#setting-threshold').value);
      try {
        await fetch('/api/settings', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ refresh_rate: rate, alarm_threshold: threshold }),
        });
        state.settings.refresh_rate = rate;
        state.settings.alarm_threshold = threshold;
        $('#footer-rate').textContent = rate;
        $('#footer-threshold').textContent = threshold;
        $('#threshold-label').textContent = threshold;
        $('#settings-overlay').classList.add('hidden');
        // 断开重连以应用新设置
        if (state.ws) state.ws.close();
      } catch (e) { console.error('保存设置失败', e); }
    });

    // 点击遮罩关闭
    $('#settings-overlay').addEventListener('click', function (e) {
      if (e.target === this) this.classList.add('hidden');
    });
  }

  // ===== CSV 导出 =====
  function initExport() {
    $('#btn-export').addEventListener('click', () => {
      window.open('/api/export/csv', '_blank');
    });
  }

  // ===== 启动 =====
  function init() {
    Particles.init('particles-canvas');
    initChart();
    initSettings();
    initExport();
    connectWebSocket();
  }

  document.addEventListener('DOMContentLoaded', init);
})();
```

- [ ] **Step 2: 验证前端可访问**

```bash
cd e:/test/project/project_6_1 && python server.py &
sleep 3 && curl -s http://localhost:8000 | head -5
```

Expected: 返回 `index.html` 内容。

---

### Task 8: 集成验证

- [ ] **Step 1: 启动后端并验证 API**

```bash
cd e:/test/project/project_6_1 && python server.py &
sleep 3
curl -s http://localhost:8000/api/settings | python -m json.tool
curl -s http://localhost:8000/api/saturation/history?limit=5 | python -m json.tool
curl -s http://localhost:8000/api/saturation/stats | python -m json.tool
```

Expected: 三个接口均返回合法 JSON。

- [ ] **Step 2: 浏览器打开页面**

在浏览器中打开 `http://localhost:8000`，确认：
- 粒子背景动画运行
- 实时值卡片显示 OneNet 数据
- 趋势图开始积累数据点
- 弧形仪表盘指针正确
- 设置弹窗可打开/保存
- CSV 导出可触发下载

- [ ] **Step 3: 对比旧版确认不影响**

```bash
streamlit run e:/test/project/project_6_1/dashboard.py &
```

旧版 Streamlit 仪表板应仍可正常访问 `http://localhost:8501`。

---
