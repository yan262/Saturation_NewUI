# -*- coding: utf-8 -*-
"""
打包脚本 — 将项目打包为单个 .exe 文件
=====================================
使用 PyInstaller 将 FastAPI + 前端 + SQLite 打包成独立的可执行文件。
打包后用户无需安装 Python 和依赖，双击 exe 即自动启动服务并打开浏览器。

使用方法:
    python build_exe.py

输出:
    dist/电缆桥架饱和度监控.exe  (约 35 MB)

原理:
    PyInstaller 将 Python 解释器 + 所有依赖 + static/ 前端文件
    全部打包进一个 .exe。运行时自动解压到临时目录，服务启动后
    自动打开浏览器访问 http://localhost:8000。
"""

import subprocess
import sys
import os

# 项目根目录
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def build():
    print("=" * 60)
    print("  Build: Cable Tray Saturation Monitor")
    print("=" * 60)
    print()

    # 第一步: 安装 PyInstaller
    print("[1/2] Checking PyInstaller ...")
    try:
        import PyInstaller
        print("       PyInstaller already installed")
    except ImportError:
        print("       Installing PyInstaller ...")
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])

    # 第二步: 执行打包
    print("[2/2] Building exe (this may take 2-5 minutes) ...")
    print()

    # PyInstaller 命令参数说明:
    #   --onefile          打包成单个 .exe
    #   --name             输出文件名
    #   --add-data         将 static/ 目录打包进 exe
    #   --hidden-import    显式声明隐式依赖
    #   --noconsole        运行时不显示命令行窗口
    #   --clean            清理临时文件
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--name", "SaturationMonitor",
        "--add-data", f"static{os.pathsep}static",
        "--add-data", f"static/fonts{os.pathsep}static/fonts",
        "--hidden-import", "auth",
        "--hidden-import", "config",
        "--hidden-import", "uvicorn.logging",
        "--hidden-import", "uvicorn.loops.auto",
        "--hidden-import", "uvicorn.protocols.http.auto",
        "--hidden-import", "uvicorn.protocols.websockets.auto",
        "--clean",
        "server.py",
    ]

    result = subprocess.run(cmd, cwd=BASE_DIR)

    # 复制启动 bat 到 dist
    import shutil
    bat_src = os.path.join(BASE_DIR, "dist", "启动.bat")
    # The .bat was manually placed or created earlier; ensure it exists
    if not os.path.exists(bat_src):
        bat_content = (
            '@echo off\r\n'
            'chcp 65001 >nul\r\n'
            'title Cable Tray Saturation Monitor\r\n'
            'echo ============================================================\r\n'
            'echo   Cable Tray Saturation Monitor v2.0\r\n'
            'echo ============================================================\r\n'
            'echo.\r\n'
            'echo   Starting server ...\r\n'
            'echo   DO NOT close this window.\r\n'
            'echo   Browser: http://localhost:8000\r\n'
            'echo   Login: admin / admin123\r\n'
            'echo ============================================================\r\n'
            'echo.\r\n'
            '"SaturationMonitor.exe"\r\n'
            'echo.\r\n'
            'echo ============================================================\r\n'
            'echo   Server stopped.\r\n'
            'echo ============================================================\r\n'
            'pause\r\n'
        )
        with open(bat_src, 'w', encoding='utf-8') as f:
            f.write(bat_content)

    if result.returncode == 0:
        exe_path = os.path.join(BASE_DIR, "dist", "SaturationMonitor.exe")
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print()
        print("=" * 60)
        print("  [OK] Build success!")
        print(f"  Output: {exe_path}")
        print(f"  Size: {size_mb:.1f} MB")
        print()
        print("  Distribute: Send these TWO files to users:")
        print("    1. SaturationMonitor.exe")
        print("    2. 启动.bat")
        print()
        print("  User: Double-click 启动.bat -> login with admin/admin123")
        print("=" * 60)
    else:
        print()
        print("[FAIL] Build failed, check errors above")
        sys.exit(1)

if __name__ == "__main__":
    build()
