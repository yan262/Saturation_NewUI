"""
电缆桥架饱和度监控仪表板 (DEPRECATED)
======================================
⚠️ 此 Streamlit 版本已弃用，不再接收功能更新。

请迁移至 FastAPI 版本:
  python server.py  →  http://localhost:8000

FastAPI 版本提供:
  - JWT 登录认证 + RBAC 权限管理
  - LDAP/AD 双模式登录
  - WebSocket 实时推送
  - 用户/角色管理界面
  - 更好的性能和安全性

如果你仍需运行此 Streamlit 版本:
  streamlit run dashboard.py
  http://localhost:8501

此版本将在后续大版本中移除。
========================
基于 Streamlit + OneNet IoT 平台，实时监控电缆桥架饱和度数据。
数据通过 SQLite 本地持久化，支持报警、趋势图、CSV 导出等功能。
"""

import streamlit as st
import requests
import time
import pandas as pd
import sqlite3
import base64
import os
from datetime import datetime
import sys

# 动态添加项目根目录到 sys.path，以便 import config
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# ================= 页面配置 =================
# 设置浏览器标签页标题、图标、宽屏布局、侧边栏默认展开
st.set_page_config(
    page_title="桥架饱和度监控",
    page_icon="⚡",
    layout="wide",                         # 宽屏模式，内容占满整个浏览器宽度
    initial_sidebar_state="expanded"       # 启动时侧边栏默认展开
)

# ⚠️ 弃用警告
st.warning(
    "⚠️ **此 Streamlit 版本已弃用，不再接收功能更新。**\n\n"
    "请迁移至 FastAPI 版本：`python server.py` → `http://localhost:8000`\n\n"
    "FastAPI 版本提供 JWT 登录、RBAC 权限、LDAP 登录、WebSocket 实时推送等高级功能。\n\n"
    "此版本将在后续大版本中移除。",
    icon="⚠️"
)

# ================= 暗色主题 CSS 注入 =================
# 通过 st.markdown 向页面注入自定义 CSS，覆盖 Streamlit 默认亮色样式
# 整个仪表板采用深蓝黑色调，类似 Grafana/Datadog 风格
DARK_CSS = """
<style>
    /* ===== 锁定页面高度，禁止整页滚动 ===== */
    html, body, #root, .stApp {
        height: 100vh !important;
        overflow: hidden !important;
    }
    .stApp {
        background: #0b1121;               /* 主背景：深蓝黑 */
    }
    /* 隐藏 Streamlit 默认顶部工具栏 */
    header[data-testid="stHeader"] {
        background: #0b1121;
        height: 0;
        overflow: hidden;
    }
    /* 主内容区容器：收紧内边距，禁止内部滚动 */
    .main .block-container {
        padding: 0 1rem !important;
        max-height: 100vh !important;
        overflow: hidden !important;
    }
    /* 侧边栏背景色 */
    section[data-testid="stSidebar"] {
        background-color: #111b30;
    }
    /* 侧边栏文字颜色统一为浅色 */
    section[data-testid="stSidebar"] .stMarkdown,
    section[data-testid="stSidebar"] label,
    section[data-testid="stSidebar"] .stSlider span {
        color: #e2e8f0 !important;
    }

    /* ===== 全局字体大小 ===== */
    html, body, .stApp, .stMarkdown, .stText {
        font-size: 17px !important;
    }
    h1 { font-size: 28px !important; color: #e2e8f0 !important; }
    h2 { font-size: 20px !important; color: #e2e8f0 !important; }
    h3 { font-size: 17px !important; color: #cbd5e1 !important; }

    /* 隐藏 Streamlit 默认的汉堡菜单、页脚和部署按钮 */
    #MainMenu { visibility: hidden; }
    footer { visibility: hidden; }
    .stDeployButton { display: none; }

    /* ===== 卡片容器 ===== */
    .card {
        background: #111b30;
        border: 1px solid #1e3a5f;
        border-radius: 10px;
        padding: 10px 14px;
        margin-bottom: 6px;
    }
    /* 卡片标题：大写、小字、灰色 */
    .card-title {
        font-size: 13px;
        color: #64748b;
        margin-bottom: 4px;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    /* 卡片主数值：大号加粗 */
    .card-value {
        font-size: 44px;
        font-weight: bold;
        line-height: 1.1;
    }
    /* 卡片副文字 */
    .card-sub {
        font-size: 13px;
        margin-top: 3px;
    }

    /* ===== 文字颜色工具类 ===== */
    .text-blue { color: #38bdf8; }
    .text-purple { color: #a78bfa; }
    .text-red { color: #f87171; }
    .text-green { color: #4ade80; }
    .text-yellow { color: #fbbf24; }
    .text-gray { color: #64748b; }

    /* ===== 报警闪烁动画 ===== */
    @keyframes blink-red {
        0%, 100% { box-shadow: 0 0 8px #f87171; }
        50% { box-shadow: 0 0 24px #ef4444, 0 0 48px #dc2626; }
    }
    /* 报警时给卡片添加红色光晕闪烁 */
    .alert-active {
        animation: blink-red 1s infinite !important;
        border-color: #f87171 !important;
    }

    /* ===== 徽章/标签 ===== */
    .badge {
        display: inline-block;
        padding: 4px 12px;
        border-radius: 10px;
        font-size: 13px;
        font-weight: 600;
    }
    .badge-normal { background: #166534; color: #4ade80; }   /* 绿色：正常 */
    .badge-warn { background: #5c3d00; color: #fbbf24; }     /* 黄色：警告 */
    .badge-danger { background: #5c1010; color: #f87171; }   /* 红色：危险 */

    /* ===== 按钮样式覆盖 ===== */
    .stButton > button {
        background: #1e3a5f !important;
        color: #38bdf8 !important;
        border: 1px solid #334155 !important;
        border-radius: 6px !important;
        font-size: 15px !important;
        padding: 8px 18px !important;
    }
    .stButton > button:hover {
        background: #253d5f !important;
        border-color: #38bdf8 !important;
    }
    /* Checkbox 和 Slider 的文字颜色 */
    .stCheckbox label span {
        font-size: 16px !important;
        color: #e2e8f0 !important;
    }
    .stSlider div {
        color: #e2e8f0 !important;
    }
    .stMetric label, .stMetric div {
        color: #e2e8f0 !important;
    }

    /* ===== 顶栏样式 ===== */
    .topbar {
        display: flex;
        justify-content: space-between;
        align-items: center;
        padding: 0 0 6px 0;
        border-bottom: 1px solid #1e3a5f;  /* 底部分割线 */
        margin-bottom: 6px;
    }
    .topbar-title {
        font-size: 26px;
        font-weight: bold;
        color: #e2e8f0;
    }
    .topbar-info {
        font-size: 14px;
        color: #94a3b8;
    }

    /* Streamlit 原生容器也加上卡片风格 */
    .st-emotion-cache-1wmy9hl,
    .st-emotion-cache-1ig9isu {
        background: #111b30;
        border: 1px solid #1e3a5f;
        border-radius: 10px;
    }
</style>
"""
# 将 CSS 注入页面
st.markdown(DARK_CSS, unsafe_allow_html=True)

# ================= OneNet IoT 平台配置 =================
# 从 config.py 读取（支持 .env 环境变量）
from config import PRODUCT_ID, DEVICE_NAME, TOKEN
API_URL = "https://iot-api.heclouds.com/thingmodel/query-device-property"   # 读取设备属性接口
STATUS_URL = "https://iot-api.heclouds.com/device/status"                    # 查询设备在线状态接口

# ================= SQLite 数据库 =================
# 数据库文件存放在项目目录下的 data/ 文件夹中
DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
DB_PATH = os.path.join(DB_DIR, "saturation.db")
os.makedirs(DB_DIR, exist_ok=True)          # 确保 data 目录存在


def init_db():
    """创建饱和度历史数据表（如果不存在）。

    表结构:
        id        - 自增主键
        timestamp - 记录时间 (如 "2026-06-12 14:30:05")
        value     - 饱和度百分比数值
    """
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
    """将一条饱和度记录写入数据库。"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO saturation_history (timestamp, value) VALUES (?, ?)",
        (timestamp_str, value)
    )
    conn.commit()
    conn.close()


def load_from_db(limit=500):
    """从数据库读取最近 N 条历史记录，按时间正序返回。"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT timestamp, value FROM saturation_history ORDER BY id DESC LIMIT ?",
        (limit,)
    )
    rows = cursor.fetchall()
    conn.close()
    return rows[::-1]                       # 倒序 → 时间正序排列


def export_csv():
    """将数据库所有记录导出为 CSV 格式字符串。"""
    conn = sqlite3.connect(DB_PATH)
    df = pd.read_sql_query("SELECT * FROM saturation_history ORDER BY id ASC", conn)
    conn.close()
    return df.to_csv(index=False)


def clear_all_data():
    """清空数据库中的所有历史记录。"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM saturation_history")
    conn.commit()
    conn.close()


def get_db_stats():
    """获取数据库统计信息：总记录数、平均值、最大值、最小值。"""
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute(
        "SELECT COUNT(*), COALESCE(AVG(value),0), COALESCE(MAX(value),0), COALESCE(MIN(value),0) "
        "FROM saturation_history"
    )
    count, avg_val, max_val, min_val = cursor.fetchone()
    conn.close()
    return count, avg_val, max_val, min_val


# ================= OneNet API 数据获取 =================

def check_device_online():
    """调用 OneNet 设备状态接口，检查设备是否在线。

    返回:
        (True,  "online")           — 设备在线
        (False, "offline")          — 设备离线
        (False, "timeout")          — 请求超时
        (False, "connection_refused") — 网络不通
        (False, "api_err:xxx")      — API 返回错误
    """
    headers = {"Authorization": TOKEN}
    params = {"product_id": PRODUCT_ID, "device_name": DEVICE_NAME}
    try:
        resp = requests.get(STATUS_URL, headers=headers, params=params, timeout=10)
        if resp.status_code != 200:
            return False, f"http_{resp.status_code}"
        data = resp.json()

        # OneNet API 返回格式：{"code": 0, "data": {"online": true/false}}
        if data.get("code") == 0 or data.get("errno") == 0:
            d = data.get("data", {})
            online = d.get("online")
            if online is not None:
                if online in (True, "true", "1", 1):
                    return True, "online"
                return False, "offline"
            status = d.get("status")
            if status is not None:
                if status in ("online", "1", 1, True):
                    return True, "online"
                return False, str(status)

        # API 返回了业务错误
        err_msg = data.get("msg", data.get("message", "api_error"))
        return False, f"api_err:{err_msg}"

    except requests.exceptions.Timeout:
        return False, "timeout"
    except requests.exceptions.ConnectionError:
        return False, "connection_refused"
    except requests.exceptions.RequestException as e:
        return False, f"net_err:{type(e).__name__}"
    except Exception as e:
        return False, f"unknown:{type(e).__name__}"


def get_onenet_data():
    """调用 OneNet 物模型接口，读取设备的 Saturation（饱和度）属性值。

    返回:
        浮点数 — 饱和度百分比（如 72.5）
        None   — 获取失败
    """
    headers = {"Authorization": TOKEN}
    params = {"product_id": PRODUCT_ID, "device_name": DEVICE_NAME}
    try:
        response = requests.get(API_URL, headers=headers, params=params, timeout=15)
        data = response.json()
        if data.get("code") == 0:
            # 遍历返回的属性列表，找到 identifier 为 "Saturation" 的那条
            properties = data.get("data", [])
            for prop in properties:
                if prop.get("identifier") == "Saturation":
                    return float(prop.get("value", 0.0))
        elif data.get("code") is not None:
            st.error(f"API 返回错误: {data.get('msg')}")
    except Exception as e:
        st.error(f"网络请求异常: {e}")
    return None


# ================= 侧边栏 =================
# 侧边栏包含监控参数设置和操作按钮
with st.sidebar:
    # 标题区
    st.markdown("""
        <div style="text-align:center; padding:8px 0;">
            <span style="font-size:36px;">⚡</span>
            <h2 style="margin:0; color:#e2e8f0; font-size:20px;">监控设置</h2>
        </div>
    """, unsafe_allow_html=True)
    st.markdown("---")

    # 刷新频率滑块：控制主循环每次 sleep 的秒数
    refresh_rate = st.slider(
        "🔄 刷新频率（秒）",
        min_value=1, max_value=10, value=2,
        help="数据刷新间隔，建议 2-5 秒"
    )

    # 报警阈值滑块：饱和度超过此值触发红色报警
    alarm_threshold = st.slider(
        "🚨 报警阈值（%）",
        min_value=30, max_value=95, value=85, step=1,
        help="饱和度超过此值触发报警"
    )

    st.markdown("---")
    # 核心开关：勾选后启动 while True 实时监控循环
    run_button = st.checkbox("🚀 开始实时监控", value=False)

    st.markdown("---")

    # 导出和清空按钮（并排）
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("📥 导出 CSV"):
            # 将数据库内容导出为 CSV 文件下载
            csv_data = export_csv()
            b64 = base64.b64encode(csv_data.encode()).decode()
            href = f'<a class="btn btn-blue" href="data:file/csv;base64,{b64}" download="saturation_data.csv">📥 下载 CSV</a>'
            st.markdown(href, unsafe_allow_html=True)
            st.success("CSV 已生成，点击上方链接下载")

    with col_b:
        if st.button("🗑 清空数据"):
            # 清空数据库 + 重置所有 session 状态
            clear_all_data()
            st.session_state.history_data = pd.DataFrame(columns=["时间", "饱和度(%)"])
            st.session_state.alarm_count = 0
            st.session_state.alarm_minutes = 0
            st.session_state.alarm_active = False
            st.session_state.prev_value = None
            st.success("数据已清空")
            st.rerun()                      # 强制刷新页面

    st.markdown("---")
    # 底部技术栈说明
    st.markdown("""
        <div style="font-size:13px; color:#64748b; text-align:center;">
            基于 Streamlit + OneNet API<br/>
            SQLite 本地持久化
        </div>
    """, unsafe_allow_html=True)


# ================= 环形仪表盘 SVG =================
# 使用纯 SVG 绘制一个半圆弧形仪表盘（类似汽车速度表）
# 左侧 180° 到 右侧 0°，底部半圆，带刻度、色区、指针

def ring_gauge_svg(value, threshold, is_alarming=False):
    """生成环形仪表盘的 SVG HTML 字符串。

    参数:
        value       — 当前饱和度值 (0-100)
        threshold   — 报警阈值
        is_alarming — 是否处于报警状态（决定是否添加闪烁动画）

    SVG 坐标说明:
        - 圆心 (150, 120)，半径 80px
        - 0° = 右侧，90° = 下方，180° = 左侧
        - 弧形从左侧 (180°) 逆时针到右侧 (0°)，画底部半圆
    """
    import math

    # --- 根据当前值决定指针颜色 ---
    if value < threshold * 0.8:
        color = "#4ade80"                   # 绿色：安全区
    elif value < threshold:
        color = "#fbbf24"                   # 黄色：警告区
    else:
        color = "#f87171"                   # 红色：危险区

    alarm_class = "alert-active" if is_alarming else ""   # 报警时添加 CSS 闪烁
    status_color = "#f87171" if is_alarming else color    # 报警时指针强制红色

    # SVG 几何参数
    r_track   = 80                          # 弧形轨道半径
    stroke_w  = 16                          # 轨道线宽
    cx, cy    = 150, 120                    # 圆心坐标
    view_w    = 300                         # SVG 视口宽度
    view_h    = 220                         # SVG 视口高度

    def svg_pt(angle_deg, dist):
        """将极坐标 (角度, 距离圆心距离) 转换为 SVG 直角坐标。"""
        a = math.radians(angle_deg)
        return cx + dist * math.cos(a), cy + dist * math.sin(a)

    # 弧形两端点（左侧 180° → 右侧 0°）
    lft = svg_pt(180, r_track)
    rgt = svg_pt(0,   r_track)
    arc_attrs = f'{r_track} {r_track} 0 0 0'    # SVG arc 参数：rx ry x-rotation large-arc sweep

    # 绿/黄/红 色区交界点（占半圆的比例）
    safe_f = min(threshold * 0.8 / 100, 1.0)     # 安全区比例
    warn_f = min(threshold        / 100, 1.0)     # 警告区比例

    g_end = svg_pt(180 - safe_f * 180, r_track)   # 绿色→黄色交界
    y_end = svg_pt(180 - warn_f * 180, r_track)   # 黄色→红色交界

    # --- 指针 ---
    frac = min(max(value / 100, 0), 1)             # 当前值占 0-100% 的比例
    nd_angle = 180 - frac * 180                    # 指针角度（100%→0°, 0%→180°）
    nd_base = svg_pt(nd_angle, r_track - 40)       # 指针尾部（靠近圆心）
    nd_tip  = svg_pt(nd_angle, r_track - 6)        # 指针尖端（靠近轨道内沿）

    # --- 刻度线和标签（0%, 20%, ..., 100%）---
    ticks = ""
    for pct in range(0, 101, 20):
        a  = 180 - pct * 1.8                       # pct=0 → 180°; pct=100 → 0°
        p1 = svg_pt(a, r_track + 5)                # 刻度线起点（外圈外）
        p2 = svg_pt(a, r_track + 14)               # 刻度线终点
        lb = svg_pt(a, r_track + 32)               # 数字标签位置
        ticks += (
            f'<line x1="{p1[0]:.1f}" y1="{p1[1]:.1f}" x2="{p2[0]:.1f}" y2="{p2[1]:.1f}" '
            f'stroke="#475569" stroke-width="1.5"/>'
            f'<text x="{lb[0]:.1f}" y="{lb[1]:.1f}" text-anchor="middle" '
            f'fill="#64748b" font-size="11">{pct}</text>'
        )

    # 组装完整 SVG
    return f"""
    <div class="card {alarm_class}" style="text-align:center;">
        <div class="card-title">🎯 实时饱和度</div>
        <svg width="100%" viewBox="0 0 {view_w} {view_h}" style="max-width:320px;">
            <!-- 底层灰色轨道 -->
            <path d="M {lft[0]:.1f} {lft[1]:.1f} A {arc_attrs} {rgt[0]:.1f} {rgt[1]:.1f}"
                  fill="none" stroke="#1e293b" stroke-width="{stroke_w}" stroke-linecap="round"/>
            <!-- 绿色安全区 -->
            <path d="M {lft[0]:.1f} {lft[1]:.1f} A {arc_attrs} {g_end[0]:.1f} {g_end[1]:.1f}"
                  fill="none" stroke="#4ade80" stroke-width="{stroke_w-4}" stroke-linecap="butt" opacity="0.88"/>
            <!-- 黄色警告区 -->
            <path d="M {g_end[0]:.1f} {g_end[1]:.1f} A {arc_attrs} {y_end[0]:.1f} {y_end[1]:.1f}"
                  fill="none" stroke="#fbbf24" stroke-width="{stroke_w-4}" stroke-linecap="butt" opacity="0.88"/>
            <!-- 红色危险区 -->
            <path d="M {y_end[0]:.1f} {y_end[1]:.1f} A {arc_attrs} {rgt[0]:.1f} {rgt[1]:.1f}"
                  fill="none" stroke="#f87171" stroke-width="{stroke_w-4}" stroke-linecap="butt" opacity="0.88"/>
            <!-- 刻度线和数字 -->
            {ticks}
            <!-- 指针 -->
            <line x1="{nd_base[0]:.1f}" y1="{nd_base[1]:.1f}" x2="{nd_tip[0]:.1f}" y2="{nd_tip[1]:.1f}"
                  stroke="{status_color}" stroke-width="2.5" stroke-linecap="round"/>
            <!-- 圆心装饰圆 -->
            <circle cx="{cx}" cy="{cy}" r="8" fill="#0b1121" stroke="{status_color}" stroke-width="2.5"/>
            <!-- 中心数值显示 -->
            <text x="{cx}" y="{cy-32}" text-anchor="middle" fill="{status_color}"
                  font-size="42" font-weight="bold">{value:.1f}%</text>
            <!-- 中心下方标签 -->
            <text x="{cx}" y="{cy+14}" text-anchor="middle" fill="#64748b"
                  font-size="12" letter-spacing="2">饱和度</text>
        </svg>
        <!-- 底部色区图例 -->
        <div style="margin-top:0; display:flex; justify-content:center; gap:14px; font-size:13px; flex-wrap:wrap;">
            <span style="color:#4ade80;">● 安全 &lt;{threshold*0.8:.0f}%</span>
            <span style="color:#fbbf24;">● 警告 {threshold*0.8:.0f}-{threshold}%</span>
            <span style="color:#f87171;">● 危险 &gt;{threshold}%</span>
        </div>
    </div>
    """


# ================= 阈值占用率进度条 =================

def threshold_bar_html(value, threshold):
    """生成阈值占用率进度条的 HTML。

    进度条表示 当前值/阈值 的百分比：
      - < 70%：绿→黄渐变
      - 70-90%：黄→红渐变
      - > 90%：红→深红渐变（接近或超过阈值）
    """
    pct = min(value / threshold * 100, 100)  # 防止超过 100%

    # 根据占用率选择渐变色
    if pct < 70:
        gradient = "linear-gradient(90deg, #4ade80, #fbbf24)"
    elif pct < 90:
        gradient = "linear-gradient(90deg, #fbbf24, #f87171)"
    else:
        gradient = "linear-gradient(90deg, #f87171, #ef4444)"

    html = f"""
    <div class="card">
        <div class="card-title">📏 阈值占用率（报警阈值: {threshold}%）</div>
        <div style="height:22px; background:#1e293b; border-radius:11px; overflow:hidden; position:relative;">
            <div style="width:{pct}%; height:100%; background:{gradient}; border-radius:11px; transition: width 0.5s ease;"></div>
        </div>
        <div style="display:flex; justify-content:space-between; margin-top:4px; font-size:14px; color:#64748b;">
            <span>0%</span>
            <span style="color:#e2e8f0; font-weight:bold;">{value:.1f}% / {threshold}%</span>
            <span>100%</span>
        </div>
    </div>
    """
    return html


# ================= 统计卡片 =================

def stat_card_html(title, value, sub_text, value_color="#38bdf8", sub_color="#64748b"):
    """生成一个统计数值卡片的 HTML。

    参数:
        title       — 卡片标题（如 "📊 实时值"）
        value       — 主数值（不含百分号）
        sub_text    — 底部副文字（如 "▲ 较上次 +2.3%"）
        value_color — 主数值颜色
        sub_color   — 副文字颜色
    """
    return f"""
    <div class="card" style="text-align:center;">
        <div class="card-title">{title}</div>
        <div class="card-value" style="color:{value_color};">{value}<span style="font-size:20px; color:#94a3b8;">%</span></div>
        <div class="card-sub" style="color:{sub_color};">{sub_text}</div>
    </div>
    """


# ================= 报警状态栏 =================

def alert_bar_html(is_alarming, threshold, alarm_count, alarm_minutes):
    """生成报警状态栏的 HTML。

    正常时：绿色徽章 "🟢 正常"
    报警时：红色徽章 "🔴 报警中" + 红色闪烁边框
    """
    if is_alarming:
        status_badge = '<span class="badge badge-danger">🔴 报警中</span>'
        bar_class = "card alert-active"     # 添加闪烁动画
    else:
        status_badge = '<span class="badge badge-normal">🟢 正常</span>'
        bar_class = "card"

    html = f"""
    <div class="{bar_class}" style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
        <div style="display:flex; align-items:center; gap:10px;">
            <span style="font-size:24px;">🚨</span>
            <span style="font-weight:bold; font-size:16px; color:#e2e8f0;">报警状态</span>
            {status_badge}
        </div>
        <div style="display:flex; gap:20px; font-size:14px; flex-wrap:wrap;">
            <span style="color:#64748b;">阈值: <span style="color:#fbbf24; font-weight:bold;">{threshold}%</span></span>
            <span style="color:#64748b;">今日报警: <span style="color:#f87171; font-weight:bold;">{alarm_count} 次</span></span>
            <span style="color:#64748b;">累计时长: <span style="color:#f87171; font-weight:bold;">{alarm_minutes} 分钟</span></span>
        </div>
    </div>
    """
    return html


# ================= Session 状态初始化 =================
# Streamlit session_state 用于在多次刷新循环间保存数据
# 每次 rerun 时不会丢失

init_db()                                   # 首次运行时创建数据库表

# 历史数据 DataFrame：列 = ["时间", "饱和度(%)"]
if "history_data" not in st.session_state:
    rows = load_from_db(limit=50)           # 从数据库恢复最近 50 条
    if rows:
        st.session_state.history_data = pd.DataFrame(
            rows, columns=["时间", "饱和度(%)"]
        )
    else:
        st.session_state.history_data = pd.DataFrame(columns=["时间", "饱和度(%)"])

# 报警相关状态
if "alarm_count" not in st.session_state:
    st.session_state.alarm_count = 0        # 今日报警次数
if "alarm_minutes" not in st.session_state:
    st.session_state.alarm_minutes = 0      # 累计报警时长（分钟）
if "alarm_active" not in st.session_state:
    st.session_state.alarm_active = False   # 当前是否处于报警状态
if "prev_value" not in st.session_state:
    st.session_state.prev_value = None      # 上一次采集的值（用于计算变化量）
if "db_save_counter" not in st.session_state:
    st.session_state.db_save_counter = 0    # 数据库写入计数器（每 3 次刷新存一次）


# ================= 顶栏 HTML 生成 =================

def topbar_html(device_online, device_status_text, refresh_rate_sec, current_time_str=""):
    """生成页面顶部状态栏的 HTML。

    根据设备在线状态显示不同的徽章：
      - None → 黄色 "检测中..."
      - True → 绿色 "设备在线" + "OneNet 已连接"
      - False → 红色 "设备离线" + "OneNet 断开"
    """
    if device_online is None:
        device_badge = '<span class="badge badge-warn">◉ 检测中...</span>'
        onenet_badge = '<span class="badge badge-warn">☁ OneNet 连接中...</span>'
    elif device_online:
        device_badge = '<span class="badge badge-normal">● 设备在线</span>'
        onenet_badge = '<span class="badge badge-normal">☁ OneNet 已连接</span>'
    else:
        device_badge = '<span class="badge badge-danger">● 设备离线</span>'
        onenet_badge = f'<span class="badge badge-danger" title="{device_status_text}">⚠ OneNet 断开</span>'

    time_display = current_time_str if current_time_str else "--:--:--"

    return f"""
    <div class="topbar">
        <div style="display:flex; align-items:center; gap:12px;">
            <span style="font-size:34px;">⚡</span>
            <span class="topbar-title">电缆桥架饱和度监控平台</span>
            {device_badge}
        </div>
        <div style="display:flex; gap:16px; align-items:center;">
            <span class="topbar-info">🔄 刷新: {refresh_rate_sec}s</span>
            <span class="topbar-info">{time_display}</span>
            {onenet_badge}
        </div>
    </div>
    """


# ================= 主页面布局 =================
# 使用 st.empty() 创建占位符，后续在循环中动态填充内容
# 页面布局从上到下分为 4 行

# 第 0 行：顶栏（全宽）
topbar_placeholder = st.empty()
topbar_placeholder.markdown(
    topbar_html(device_online=None, device_status_text="",
                refresh_rate_sec=refresh_rate, current_time_str=""),
    unsafe_allow_html=True
)

# 第 1 行：左侧环形仪表盘 (1/3) | 右侧 2×2 统计卡片网格 (2/3)
left_col, right_col = st.columns([1, 2])

gauge_placeholder = left_col.empty()        # 仪表盘占位

with right_col:
    cr1 = st.columns(2)                     # 上排两列
    cr2 = st.columns(2)                     # 下排两列

# 4 个卡片占位符：实时值、今日平均、最大值、最小值
card_placeholders = [
    cr1[0].empty(), cr1[1].empty(),
    cr2[0].empty(), cr2[1].empty(),
]

# 第 2 行：阈值占用率进度条（全宽）
progress_placeholder = st.empty()

# 第 3 行：报警状态栏 (3/5) | 迷你趋势图 (2/5)
alert_col, chart_col = st.columns([3, 2])

alert_placeholder = alert_col.empty()
chart_placeholder = chart_col.empty()


# ================= 实时刷新循环 =================
# 当用户勾选侧边栏的 "🚀 开始实时监控" 后，进入无限循环
# 每次循环：采集数据 → 更新所有 UI 占位符 → sleep

if run_button:
    while True:
        # 获取当前时间字符串
        current_time = datetime.now().strftime("%H:%M:%S")          # 仅时间，用于图表 X 轴
        current_full = datetime.now().strftime("%Y-%m-%d %H:%M:%S") # 完整时间，用于数据库存储

        # 步骤 1：直接采集 OneNet 数据（不检查设备在线状态）
        sat_value = get_onenet_data()
        topbar_placeholder.markdown(
            topbar_html(device_online=True if sat_value is not None else False,
                        device_status_text="直接采集模式",
                        refresh_rate_sec=refresh_rate,
                        current_time_str=current_time),
            unsafe_allow_html=True
        )

        # 步骤 2：数据获取成功 → 更新所有显示组件
        if sat_value is not None:
            # --- 报警判断 ---
            is_alarming = sat_value >= alarm_threshold
            # 刚触发报警时计数 +1（防止同一轮报警重复计数）
            if is_alarming and not st.session_state.alarm_active:
                st.session_state.alarm_count += 1
            st.session_state.alarm_active = is_alarming
            # 报警状态下累计时长
            if is_alarming:
                st.session_state.alarm_minutes += refresh_rate / 60.0

            # --- 数据持久化（每 3 次刷新写一次数据库，减少磁盘 IO）---
            st.session_state.db_save_counter += 1
            if st.session_state.db_save_counter >= 3:
                save_to_db(current_full, sat_value)
                st.session_state.db_save_counter = 0

            # --- 计算相对上次的变化量 ---
            prev_val = st.session_state.prev_value
            if prev_val is not None:
                diff = sat_value - prev_val
                diff_text = f"▲ 较上次 +{diff:.1f}%" if diff > 0 else f"▼ 较上次 {diff:.1f}%"
                # 变化量颜色：下降=绿，微涨=灰，大涨(>3%)=红
                diff_color = "#4ade80" if diff <= 0 else "#f87171" if diff > 3 else "#94a3b8"
            else:
                diff_text = "首次采集"
                diff_color = "#64748b"
            st.session_state.prev_value = sat_value

            # --- 更新历史数据 DataFrame（只保留最近 50 条）---
            new_row = pd.DataFrame([{"时间": current_time, "饱和度(%)": sat_value}])
            st.session_state.history_data = pd.concat(
                [st.session_state.history_data, new_row], ignore_index=True
            )
            if len(st.session_state.history_data) > 50:
                st.session_state.history_data = st.session_state.history_data.iloc[-50:]

            # --- 计算统计指标 ---
            hist_vals = st.session_state.history_data["饱和度(%)"]
            display_avg = hist_vals.mean() if len(hist_vals) > 0 else 0
            display_max = hist_vals.max() if len(hist_vals) > 0 else 0
            display_min = hist_vals.min() if len(hist_vals) > 0 else 0

            # 找到最大值和最小值对应的时间
            max_time_row = st.session_state.history_data.loc[
                st.session_state.history_data["饱和度(%)"].idxmax()
            ] if len(hist_vals) > 0 else None
            min_time_row = st.session_state.history_data.loc[
                st.session_state.history_data["饱和度(%)"].idxmin()
            ] if len(hist_vals) > 0 else None

            # ===== 渲染所有 UI 组件 =====

            # 行 1 左侧：环形仪表盘
            gauge_placeholder.markdown(
                ring_gauge_svg(sat_value, alarm_threshold, is_alarming),
                unsafe_allow_html=True
            )

            # 行 1 右侧：4 个统计卡片
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

            # 行 2：阈值占用率进度条
            progress_placeholder.markdown(
                threshold_bar_html(sat_value, alarm_threshold),
                unsafe_allow_html=True
            )

            # 行 3：报警状态栏 + 迷你趋势图（左右并排）
            alert_placeholder.markdown(
                alert_bar_html(
                    st.session_state.alarm_active,
                    alarm_threshold,
                    st.session_state.alarm_count,
                    int(st.session_state.alarm_minutes)
                ),
                unsafe_allow_html=True
            )
            chart_placeholder.area_chart(
                st.session_state.history_data.set_index("时间"),
                color="#38bdf8",
                height=120,
            )

        else:
            # 数据获取失败时：仪表盘区域显示错误提示
            gauge_placeholder.markdown(f"""
                <div class="card" style="text-align:center; padding:30px;">
                    <span style="font-size:40px;">⚠️</span>
                    <p style="color:#f87171; font-size:14px;">数据获取失败</p>
                    <p style="color:#64748b; font-size:12px;">OneNet API 返回异常，请检查网络连接</p>
                </div>
            """, unsafe_allow_html=True)

        # 等待指定秒数后进入下一次循环
        time.sleep(refresh_rate)

else:
    # ===== 初始空闲状态（未勾选开始监控）=====
    current_time_idle = datetime.now().strftime("%H:%M:%S")
    topbar_placeholder.markdown(
        topbar_html(device_online=None,
                    device_status_text="等待启动",
                    refresh_rate_sec=refresh_rate,
                    current_time_str=current_time_idle),
        unsafe_allow_html=True
    )
    gauge_placeholder.markdown("""
        <div class="card" style="text-align:center; padding:30px;">
            <span style="font-size:40px;">⚡</span>
            <p style="color:#94a3b8; font-size:14px;">等待开始监控...</p>
        </div>
    """, unsafe_allow_html=True)
    # 提示用户操作
    st.info("👈 请在左侧勾选 **🚀 开始实时监控**")
