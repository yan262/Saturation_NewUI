# 电缆桥架饱和度仪表盘全面升级 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将简洁的 Streamlit 仪表盘升级为暗色科技风全面监控平台，包含环形仪表盘、统计卡片、智能报警、阈值进度条、历史表格、SQLite 持久化 6 大模块。

**Architecture:** 单文件 `dashboard.py`，CSS 通过 `st.markdown` 注入。数据流：OneNet API → 内存 DataFrame → SQLite 持久化 → Streamlit UI 渲染。页面使用 CSS Grid/Flexbox 自定义布局，替代 Streamlit 默认列布局。

**Tech Stack:** Python 3, Streamlit, requests, pandas, sqlite3, base64

---

### Task 1: 暗色主题 CSS 与全局样式

**Files:**
- Modify: `E:\test\project\project_6_1\dashboard.py` (整体重写)

- [ ] **Step 1: 创建新的 dashboard.py 文件骨架，注入暗色主题 CSS**

将整个文件替换为以下内容（后续 Task 逐步填充功能模块）：

```python
import streamlit as st
import requests
import time
import pandas as pd
import sqlite3
import base64
import os
from datetime import datetime

# ================= 页面配置 =================
st.set_page_config(
    page_title="桥架饱和度监控",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ================= 暗色主题 CSS 注入 =================
DARK_CSS = """
<style>
    /* 全局背景与字体 */
    .stApp {
        background: #0b1121;
    }
    header[data-testid="stHeader"] {
        background: #0b1121;
    }
    section[data-testid="stSidebar"] {
        background-color: #111b30;
    }
    section[data-testid="stSidebar"] .stMarkdown,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] .stSlider span {
        color: #e2e8f0 !important;
    }

    /* 全局字体放大 */
    html, body, .stApp, .stMarkdown, .stText {
        font-size: 16px !important;
    }
    h1 { font-size: 28px !important; color: #e2e8f0 !important; }
    h2 { font-size: 22px !important; color: #e2e8f0 !important; }
    h3 { font-size: 18px !important; color: #cbd5e1 !important; }

    /* 隐藏 Streamlit 默认元素 */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    .stDeployButton { display: none; }

    /* 自定义卡片 */
    .card {
        background: #111b30;
        border: 1px solid #1e3a5f;
        border-radius: 12px;
        padding: 18px;
        margin-bottom: 12px;
    }
    .card-title {
        font-size: 13px;
        color: #64748b;
        margin-bottom: 6px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    .card-value {
        font-size: 42px;
        font-weight: bold;
        line-height: 1.1;
    }
    .card-sub {
        font-size: 12px;
        margin-top: 4px;
    }

    /* 颜色工具类 */
    .text-blue { color: #38bdf8; }
    .text-purple { color: #a78bfa; }
    .text-red { color: #f87171; }
    .text-green { color: #4ade80; }
    .text-yellow { color: #fbbf24; }
    .text-gray { color: #64748b; }

    /* 报警闪烁动画 */
    @keyframes blink-red {
        0%, 100% { box-shadow: 0 0 8px #f87171; }
        50% { box-shadow: 0 0 24px #ef4444, 0 0 48px #dc2626; }
    }
    .alert-active {
        animation: blink-red 1s infinite !important;
        border-color: #f87171 !important;
    }

    /* 状态标签 */
    .badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 12px;
        font-size: 13px;
        font-weight: 600;
    }
    .badge-normal { background: #166534; color: #4ade80; }
    .badge-warn { background: #5c3d00; color: #fbbf24; }
    .badge-danger { background: #5c1010; color: #f87171; }

    /* 表格暗色样式 */
    .dark-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 15px;
    }
    .dark-table th {
        background: #0d1525;
        color: #64748b;
        padding: 10px 14px;
        text-align: left;
        border-bottom: 1px solid #1e3a5f;
        font-size: 13px;
        text-transform: uppercase;
        letter-spacing: 0.5px;
    }
    .dark-table td {
        padding: 9px 14px;
        border-bottom: 1px solid #1a2744;
        color: #cbd5e1;
    }

    /* 按钮 */
    .btn {
        display: inline-block;
        padding: 8px 18px;
        border-radius: 6px;
        font-size: 14px;
        font-weight: 600;
        cursor: pointer;
        border: none;
        text-decoration: none;
    }
    .btn-blue { background: #1e3a5f; color: #38bdf8; }
    .btn-green { background: #166534; color: #4ade80; }

    /* Streamlit 组件覆盖 */
    .stButton > button {
        background: #1e3a5f !important;
        color: #38bdf8 !important;
        border: 1px solid #334155 !important;
        border-radius: 6px !important;
        font-size: 14px !important;
        padding: 8px 18px !important;
    }
    .stButton > button:hover {
        background: #253d5f !important;
        border-color: #38bdf8 !important;
    }
    .stCheckbox label span {
        font-size: 15px !important;
        color: #e2e8f0 !important;
    }
    .stSlider div {
        color: #e2e8f0 !important;
    }
    .stMetric label, .stMetric div {
        color: #e2e8f0 !important;
    }

    /* 顶栏 */
    .topbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 12px 0;
        border-bottom: 1px solid #1e3a5f;
        margin-bottom: 16px;
    }
    .topbar-title {
        font-size: 22px;
        font-weight: bold;
        color: #e2e8f0;
    }
    .topbar-info {
        font-size: 14px;
        color: #94a3b8;
    }
</style>
"""
st.markdown(DARK_CSS, unsafe_allow_html=True)
```

- [ ] **Step 2: 验证基础骨架**

运行: `streamlit run E:\test\project\project_6_1\dashboard.py`
预期: 页面加载，暗色背景、无报错（此时页面内容为空）

---

### Task 2: OneNet 配置与数据获取 + SQLite 持久化

**Files:**
- Modify: `E:\test\project\project_6_1\dashboard.py` (追加代码)

- [ ] **Step 1: 在 CSS 之后追加 OneNet 配置与数据库初始化代码**

```python
# ================= OneNet 配置 =================
PRODUCT_ID = "IqV8M48sQQ"
DEVICE_NAME = "Saturation_Detection"
TOKEN = "version=2018-10-31&res=products%2FIqV8M48sQQ%2Fdevices%2FSaturation_Detection&et=2058447118&method=md5&sign=rzM7OnlFyCMOexl5ixFGYQ%3D%3D"
API_URL = "https://iot-api.heclouds.com/thingmodel/query-device-property"

# ================= SQLite 数据库初始化 =================
DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "saturation.db")
os.makedirs(DB_DIR, exist_ok=True)

def init_db():
    """初始化数据库表"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS saturation_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            value REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def save_to_db(timestamp_str, value):
    """保存一条记录到 SQLite"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO saturation_history (timestamp, value) VALUES (?, ?)",
        (timestamp_str, value)
    )
    conn.commit()
    conn.close()

def load_from_db(limit=500):
    """从 SQLite 加载最近 N 条记录"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT timestamp, value FROM saturation_history ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    return rows[::-1]  # 时间升序

def export_csv():
    """导出全部数据为 CSV 字符串"""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM saturation_history ORDER BY id ASC", conn)
    conn.close()
    return df.to_csv(index=False)

def clear_all_data():
    """清空历史数据"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM saturation_history")
    conn.commit()
    conn.close()

def get_db_stats():
    """获取数据库统计信息"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*), COALESCE(AVG(value),0), COALESCE(MAX(value),0), COALESCE(MIN(value),0) FROM saturation_history")
    count, avg_val, max_val, min_val = cursor.fetchone()
    conn.close()
    return count, avg_val, max_val, min_val
```

- [ ] **Step 2: 追加 OneNet API 调用函数**

```python
# ================= OneNet 数据获取 =================
def get_onenet_data():
    """通过 OneNet HTTP API 获取物模型属性(Saturation)"""
    headers = {"Authorization": TOKEN}
    params = {"product_id": PRODUCT_ID, "device_name": DEVICE_NAME}
    try:
        response = requests.get(API_URL, headers=headers, params=params, timeout=15)
        data = response.json()
        if data.get("code") == 0:
            properties = data.get("data", [])
            for prop in properties:
                if prop.get("identifier") == "Saturation":
                    return float(prop.get("value", 0.0))
        else:
            st.error(f"API 错误: {data.get('msg')}")
    except Exception as e:
        st.error(f"网络异常: {e}")
    return None
```

- [ ] **Step 3: 验证数据获取**

在文件末尾临时添加测试代码，运行确认 API 通畅。

---

### Task 3: 侧边栏控制面板

**Files:**
- Modify: `E:\test\project\project_6_1\dashboard.py` (追加侧边栏代码)

- [ ] **Step 1: 追加侧边栏代码**

```python
# ================= 侧边栏 =================
with st.sidebar:
    st.markdown("""
        <div style="text-align:center; padding:10px 0;">
            <span style="font-size:36px;">⚡</span>
            <h2 style="margin:0; color:#e2e8f0;">监控设置</h2>
        </div>
    """, unsafe_allow_html=True)
    st.markdown("---")

    refresh_rate = st.slider(
        "🔄 刷新频率（秒）",
        min_value=1, max_value=10, value=2,
        help="数据刷新间隔，建议 2-5 秒"
    )

    alarm_threshold = st.slider(
        "🚨 报警阈值（%）",
        min_value=70, max_value=95, value=85, step=1,
        help="饱和度超过此值触发报警"
    )

    st.markdown("---")
    run_button = st.checkbox("🚀 开始实时监控", value=False)

    st.markdown("---")

    # CSV 导出按钮
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("📥 导出 CSV"):
            csv_data = export_csv()
            b64 = base64.b64encode(csv_data.encode()).decode()
            href = f'<a class="btn btn-blue" href="data:file/csv;base64,{b64}" download="saturation_data.csv">📥 下载 CSV</a>'
            st.markdown(href, unsafe_allow_html=True)
            st.success("CSV 已生成，点击上方链接下载")

    with col_b:
        if st.button("🗑 清空数据"):
            clear_all_data()
            st.session_state.history_data = pd.DataFrame(columns=["时间", "饱和度(%)"])
            st.success("数据已清空")
            st.rerun()

    st.markdown("---")
    st.markdown("""
        <div style="font-size:12px; color:#64748b; text-align:center;">
            基于 Streamlit + OneNet API<br/>
            SQLite 本地持久化
        </div>
    """, unsafe_allow_html=True)
```

---

### Task 4: 环形仪表盘 SVG + 阈值进度条

**Files:**
- Modify: `E:\test\project\project_6_1\dashboard.py` (追加函数)

- [ ] **Step 1: 追加环形仪表盘生成函数**

```python
# ================= 环形仪表盘 SVG 生成 =================
def ring_gauge_svg(value, threshold, is_alarming=False):
    """生成环形仪表盘 SVG HTML 字符串"""
    # value 映射到角度：0% → -210°, 100% → 30° (共 240° 弧)
    pct = min(value / 100.0, 1.0)
    angle = -210 + (240 * pct)

    # 颜色分级
    if value < threshold * 0.8:
        color = "#4ade80"
    elif value < threshold:
        color = "#fbbf24"
    else:
        color = "#f87171"

    # 三色弧段角度 (绿0-70%, 黄70-85%, 红85-100%)
    green_start = -210
    green_end = -210 + 240 * 0.70
    yellow_start = green_end
    yellow_end = -210 + 240 * 0.85
    red_start = yellow_end
    red_end = 30

    radius = 80
    stroke_width = 14
    center = 110
    circum = 2 * 3.14159 * radius
    arc_length = (240 / 360) * circum
    dash_offset = (360 - 240) / 360 * circum * (-210 / 360 * 360)  # simplified below

    # 实际实现用简化坐标计算
    polar_to_cart = lambda r, deg: (
        center + r * 0.001 * (90 - deg) * 1.5,  # 简化，实际用 trig
        center - r * 0.001 * deg * 1.5
    )

    alarm_class = "alert-active" if is_alarming else ""
    status_color = color
    if is_alarming:
        status_color = "#f87171"

    html = f"""
    <div class="card {alarm_class}" style="text-align:center;">
        <div class="card-title">🎯 实时饱和度</div>
        <svg width="220" height="180" viewBox="0 0 220 180">
            <!-- 背景弧 -->
            <path d="M 30 160 A 80 80 0 0 1 190 160"
                  fill="none" stroke="#1e293b" stroke-width="{stroke_width}" stroke-linecap="round"/>
            <!-- 绿色段 0-70% -->
            <path d="M 33.5 160 A 80 80 0 0 1 145 37.5"
                  fill="none" stroke="#4ade80" stroke-width="{stroke_width-2}" stroke-linecap="butt" opacity="0.9"/>
            <!-- 黄色段 70-85% -->
            <path d="M 145 37.5 A 80 80 0 0 1 175 30.5"
                  fill="none" stroke="#fbbf24" stroke-width="{stroke_width-2}" stroke-linecap="butt" opacity="0.9"/>
            <!-- 红色段 85-100% -->
            <path d="M 175 30.5 A 80 80 0 0 1 186.5 160"
                  fill="none" stroke="#f87171" stroke-width="{stroke_width-2}" stroke-linecap="butt" opacity="0.9"/>
            <!-- 指针线 -->
            <line x1="{center}" y1="{center + 25}" x2="{center + 60 * 0.6}" y2="{center - 60 * 0.8}"
                  stroke="{status_color}" stroke-width="3" stroke-linecap="round"
                  transform="rotate({angle - (-60)}, {center}, {center + 25})"/>
            <!-- 中心圆点 -->
            <circle cx="{center}" cy="{center + 25}" r="8" fill="{status_color}"/>
        </svg>
        <div class="card-value" style="color:{status_color}; font-size:56px; margin-top:-10px;">
            {value:.1f}<span style="font-size:22px; color:#94a3b8;">%</span>
        </div>
        <div style="margin-top:4px; display:flex; justify-content:center; gap:16px; font-size:12px;">
            <span style="color:#4ade80;">● 安全 &lt;{threshold*0.8:.0f}</span>
            <span style="color:#fbbf24;">● 警告 {threshold*0.8:.0f}-{threshold}</span>
            <span style="color:#f87171;">● 危险 &gt;{threshold}</span>
        </div>
    </div>
    """
    return html
```

- [ ] **Step 2: 追加阈值进度条生成函数**

```python
def threshold_bar_html(value, threshold):
    """生成阈值进度条 HTML"""
    pct = min(value / threshold * 100, 100)
    if pct < 70:
        gradient = "linear-gradient(90deg, #4ade80, #fbbf24)"
    elif pct < 90:
        gradient = "linear-gradient(90deg, #fbbf24, #f87171)"
    else:
        gradient = "linear-gradient(90deg, #f87171, #ef4444)"

    html = f"""
    <div class="card">
        <div class="card-title">📏 阈值占用率（报警阈值: {threshold}%）</div>
        <div style="height:26px; background:#1e293b; border-radius:13px; overflow:hidden; position:relative;">
            <div style="width:{pct}%; height:100%; background:{gradient}; border-radius:13px; transition: width 0.5s ease;"></div>
        </div>
        <div style="display:flex; justify-content:space-between; margin-top:6px; font-size:13px; color:#64748b;">
            <span>0%</span>
            <span style="color:#e2e8f0; font-weight:bold;">{value:.1f}% / {threshold}%</span>
            <span>100%</span>
        </div>
    </div>
    """
    return html
```

---

### Task 5: 顶部栏 + 统计卡片 + 状态标签 + 趋势图 + 报警栏 + 历史表格

**Files:**
- Modify: `E:\test\project\project_6_1\dashboard.py` (追加渲染函数)

- [ ] **Step 1: 追加统计卡片渲染函数**

```python
# ================= 统计卡片 =================
def stat_card_html(title, value, sub_text, value_color="#38bdf8", sub_color="#64748b"):
    """生成统计卡片 HTML"""
    return f"""
    <div class="card" style="text-align:center;">
        <div class="card-title">{title}</div>
        <div class="card-value" style="color:{value_color};">{value}<span style="font-size:18px; color:#94a3b8;">%</span></div>
        <div class="card-sub" style="color:{sub_color};">{sub_text}</div>
    </div>
    """
```

- [ ] **Step 2: 追加报警栏渲染函数**

```python
def alert_bar_html(is_alarming, threshold, alarm_count, alarm_minutes):
    """生成报警状态栏 HTML"""
    if is_alarming:
        status_badge = '<span class="badge badge-danger">🔴 报警中</span>'
        bar_class = "card alert-active"
    else:
        status_badge = '<span class="badge badge-normal">🟢 正常</span>'
        bar_class = "card"

    html = f"""
    <div class="{bar_class}" style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:12px;">
        <div style="display:flex; align-items:center; gap:12px;">
            <span style="font-size:24px;">🚨</span>
            <span style="font-weight:bold; font-size:16px; color:#e2e8f0;">报警状态</span>
            {status_badge}
        </div>
        <div style="display:flex; gap:28px; font-size:14px;">
            <span style="color:#64748b;">阈值: <span style="color:#fbbf24; font-weight:bold;">{threshold}%</span></span>
            <span style="color:#64748b;">今日报警: <span style="color:#f87171; font-weight:bold;">{alarm_count} 次</span></span>
            <span style="color:#64748b;">累计时长: <span style="color:#f87171; font-weight:bold;">{alarm_minutes} 分钟</span></span>
        </div>
    </div>
    """
    return html
```

- [ ] **Step 3: 追加历史数据表格渲染函数**

```python
def history_table_html(df, limit=20):
    """生成历史数据暗色表格 HTML"""
    df_display = df.tail(limit).iloc[::-1]  # 最新的在前
    rows_html = ""
    for i, (_, row) in enumerate(df_display.iterrows()):
        sat_val = row["饱和度(%)"]
        if sat_val >= 85:
            status = '<span style="color:#f87171;">● 危险</span>'
        elif sat_val >= 70:
            status = '<span style="color:#fbbf24;">● 警告</span>'
        else:
            status = '<span style="color:#4ade80;">● 正常</span>'
        rows_html += f"""
        <tr>
            <td style="color:#64748b;">{i+1}</td>
            <td>{row['时间']}</td>
            <td style="text-align:right; color:#38bdf8; font-weight:bold;">{sat_val:.1f}%</td>
            <td style="text-align:center;">{status}</td>
        </tr>"""

    html = f"""
    <div class="card">
        <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:12px;">
            <span style="font-size:16px; color:#cbd5e1;">📋 历史数据（最近 {limit} 条）</span>
            <span class="badge badge-normal">💾 已持久化</span>
        </div>
        <div style="overflow-x:auto;">
            <table class="dark-table">
                <thead>
                    <tr>
                        <th>#</th>
                        <th>时间</th>
                        <th style="text-align:right;">饱和度</th>
                        <th style="text-align:center;">状态</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
        </div>
    </div>
    """
    return html
```

---

### Task 6: 主页面布局整合与实时刷新逻辑

**Files:**
- Modify: `E:\test\project\project_6_1\dashboard.py` (追加主逻辑)

- [ ] **Step 1: 追加 session 初始化与主布局代码**

```python
# ================= Session 状态初始化 =================
init_db()

if "history_data" not in st.session_state:
    # 从 SQLite 加载历史数据
    rows = load_from_db(limit=50)
    if rows:
        st.session_state.history_data = pd.DataFrame(
            rows, columns=["时间", "饱和度(%)"]
        )
    else:
        st.session_state.history_data = pd.DataFrame(columns=["时间", "饱和度(%)"])

if "alarm_count" not in st.session_state:
    st.session_state.alarm_count = 0
if "alarm_minutes" not in st.session_state:
    st.session_state.alarm_minutes = 0
if "alarm_active" not in st.session_state:
    st.session_state.alarm_active = False
if "prev_value" not in st.session_state:
    st.session_state.prev_value = None
if "db_save_counter" not in st.session_state:
    st.session_state.db_save_counter = 0

# ================= 主页面布局 =================
# 顶栏
st.markdown(f"""
<div class="topbar">
    <div style="display:flex; align-items:center; gap:12px;">
        <span style="font-size:26px;">⚡</span>
        <span class="topbar-title">电缆桥架饱和度监控平台</span>
        <span class="badge badge-normal">● 在线</span>
    </div>
    <div style="display:flex; gap:20px; align-items:center;">
        <span class="topbar-info">🔄 刷新: {refresh_rate}s</span>
        <span class="topbar-info" id="current-time">--:--:--</span>
        <span class="badge badge-normal">☁ OneNet 已连接</span>
    </div>
</div>
""", unsafe_allow_html=True)

# 左侧：环形仪表盘 + 进度条（2:5 比例）
left_col, right_col = st.columns([2, 5])

gauge_placeholder = left_col.empty()
progress_placeholder = left_col.empty()

# 右侧：4 统计卡片
card_cols = right_col.columns(4)
card_placeholders = [c.empty() for c in card_cols]

# 趋势图
chart_title_placeholder = right_col.empty()
chart_placeholder = right_col.empty()

# 报警栏
alert_placeholder = st.empty()

# 历史表格
table_placeholder = st.empty()
```

- [ ] **Step 2: 追加实时刷新循环**

```python
# ================= 实时刷新逻辑 =================
if run_button:
    while True:
        sat_value = get_onenet_data()
        current_time = datetime.now().strftime("%H:%M:%S")
        current_full = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        if sat_value is not None:
            # --- 报警判断 ---
            is_alarming = sat_value >= alarm_threshold
            if is_alarming and not st.session_state.alarm_active:
                st.session_state.alarm_count += 1
            prev_alarm = st.session_state.alarm_active
            st.session_state.alarm_active = is_alarming
            if is_alarming:
                st.session_state.alarm_minutes += refresh_rate / 60.0

            # --- 持久化（每 3 次刷新存一次，避免频繁写入）---
            st.session_state.db_save_counter += 1
            if st.session_state.db_save_counter >= 3:
                save_to_db(current_full, sat_value)
                st.session_state.db_save_counter = 0

            # --- 计算变化量 ---
            prev_val = st.session_state.prev_value
            if prev_val is not None:
                diff = sat_value - prev_val
                diff_text = f"▲ 较上次 +{diff:.1f}%" if diff > 0 else f"▼ 较上次 {diff:.1f}%"
                diff_color = "#4ade80" if diff <= 0 else "#f87171" if diff > 3 else "#94a3b8"
            else:
                diff_text = "首次采集"
                diff_color = "#64748b"
            st.session_state.prev_value = sat_value

            # --- 更新历史 DataFrame ---
            new_row = pd.DataFrame([{"时间": current_time, "饱和度(%)": sat_value}])
            st.session_state.history_data = pd.concat(
                [st.session_state.history_data, new_row], ignore_index=True
            )
            if len(st.session_state.history_data) > 50:
                st.session_state.history_data = st.session_state.history_data.iloc[-50:]

            # --- 获取统计 ---
            db_count, db_avg, db_max, db_min = get_db_stats()
            hist_vals = st.session_state.history_data["饱和度(%)"]
            display_avg = hist_vals.mean() if len(hist_vals) > 0 else 0
            display_max = hist_vals.max() if len(hist_vals) > 0 else 0
            display_min = hist_vals.min() if len(hist_vals) > 0 else 0

            max_time_row = st.session_state.history_data.loc[
                st.session_state.history_data["饱和度(%)"].idxmax()
            ] if len(hist_vals) > 0 else None
            min_time_row = st.session_state.history_data.loc[
                st.session_state.history_data["饱和度(%)"].idxmin()
            ] if len(hist_vals) > 0 else None

            # --- 渲染左侧：环形仪表盘 + 进度条 ---
            gauge_placeholder.markdown(
                ring_gauge_svg(sat_value, alarm_threshold, is_alarming),
                unsafe_allow_html=True
            )
            progress_placeholder.markdown(
                threshold_bar_html(sat_value, alarm_threshold),
                unsafe_allow_html=True
            )

            # --- 渲染统计卡片 ---
            cards_data = [
                ("📊 实时值", f"{sat_value:.1f}", diff_text, "#38bdf8", diff_color),
                ("📈 今日平均", f"{display_avg:.1f}", f"采样 {len(hist_vals)} 次", "#a78bfa", "#64748b"),
                ("🔺 最大值", f"{display_max:.1f}",
                 f"{max_time_row['时间']} 出现" if max_time_row is not None else "",
                 "#f87171", "#64748b"),
                ("🔽 最小值", f"{display_min:.1f}",
                 f"{min_time_row['时间']} 出现" if min_time_row is not None else "",
                 "#4ade80", "#64748b"),
            ]
            for idx, (title, val, sub, vc, sc) in enumerate(cards_data):
                card_placeholders[idx].markdown(
                    stat_card_html(title, val, sub, vc, sc),
                    unsafe_allow_html=True
                )

            # --- 渲染趋势图 ---
            chart_title_placeholder.markdown(
                '<div style="font-size:16px; color:#cbd5e1; margin-top:8px;">📈 实时饱和度趋势（最近 50 条）</div>',
                unsafe_allow_html=True
            )
            # 使用 Streamlit 原生 area_chart（面积填充）
            chart_placeholder.area_chart(
                st.session_state.history_data.set_index("时间"),
                color="#38bdf8",
                height=280,
            )

            # --- 渲染报警栏 ---
            alert_placeholder.markdown(
                alert_bar_html(
                    st.session_state.alarm_active,
                    alarm_threshold,
                    st.session_state.alarm_count,
                    int(st.session_state.alarm_minutes)
                ),
                unsafe_allow_html=True
            )

            # --- 渲染历史表格 ---
            table_placeholder.markdown(
                history_table_html(st.session_state.history_data, limit=20),
                unsafe_allow_html=True
            )

        else:
            # 数据获取失败
            gauge_placeholder.markdown("""
                <div class="card" style="text-align:center; padding:40px;">
                    <span style="font-size:48px;">⚠️</span>
                    <p style="color:#f87171; font-size:16px;">数据获取失败</p>
                </div>
            """, unsafe_allow_html=True)

        time.sleep(refresh_rate)
else:
    # 初始空状态
    gauge_placeholder.markdown("""
        <div class="card" style="text-align:center; padding:30px;">
            <span style="font-size:48px;">⚡</span>
            <p style="color:#94a3b8; font-size:16px;">等待开始监控...</p>
        </div>
    """, unsafe_allow_html=True)
    st.info("👈 请在左侧勾选 **🚀 开始实时监控**")
```

---

### Task 7: 完整整合与验证

**Files:**
- Verify: `E:\test\project\project_6_1\dashboard.py`

- [ ] **Step 1: 确认所有 Task 的代码片段按顺序整合到 dashboard.py**

最终文件结构应为：
1. import 语句
2. 页面配置
3. DARK_CSS 样式注入
4. OneNet 配置
5. SQLite 函数（init_db, save_to_db, load_from_db, export_csv, clear_all_data, get_db_stats）
6. get_onenet_data()
7. 侧边栏
8. SVG 函数（ring_gauge_svg, threshold_bar_html）
9. 渲染函数（stat_card_html, alert_bar_html, history_table_html）
10. Session 初始化
11. 主布局 + 实时刷新循环

- [ ] **Step 2: 启动验证**

```bash
cd E:\test\project\project_6_1 && streamlit run dashboard.py
```

检查清单：
- [ ] 暗色主题正常显示
- [ ] 侧边栏控件可操作
- [ ] 勾选"开始实时监控"后数据拉取正常
- [ ] 环形仪表盘显示饱和度，颜色分级正确
- [ ] 4 个统计卡片数据正确
- [ ] 趋势面积图实时更新
- [ ] 阈值进度条比例正确
- [ ] 报警栏状态根据阈值变化
- [ ] 历史表格显示最近 20 条
- [ ] CSV 导出按钮可生成下载链接
- [ ] SQLite 数据文件自动创建在 data/ 目录

- [ ] **Step 3: 将 data/ 加入 .gitignore**

```bash
echo "data/" >> E:\test\project\project_6_1\.gitignore
```

---

### Task 8: 关闭 Visual Companion 服务

**Files:**
- No files changed

- [ ] **Step 1: 停止 visual companion 服务**

```bash
bash "C:\Users\lenovo\.claude\plugins\cache\claude-plugins-official\superpowers\5.1.0\skills\brainstorming\scripts\stop-server.sh" "E:\test\project\project_6_1\.superpowers\brainstorm\478-1780981227"
```
