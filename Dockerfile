# 电缆桥架饱和度监控系统 — Dockerfile
# =====================================
# 构建: docker build -t saturation-monitor .
# 运行: docker run -p 8000:8000 --env-file .env -v ./data:/app/data saturation-monitor
#
# 或使用 docker-compose: docker compose up -d

FROM python:3.12-slim

LABEL maintainer="Saturation Monitor Team"
LABEL description="电缆桥架饱和度监控系统 — FastAPI + OneNet IoT"

# 设置工作目录
WORKDIR /app

# 安装系统依赖（ldap3 需要 libldap）
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libldap2-dev \
        libsasl2-dev \
    && rm -rf /var/lib/apt/lists/*

# 先复制依赖文件，利用 Docker 缓存层
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY server.py auth.py config.py logger.py database.py ./
COPY static/ ./static/

# 创建数据目录（运行时可挂载外部卷）
RUN mkdir -p /app/data

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/docs')" || exit 1

# 使用 uvicorn 启动（无热重载，适合生产）
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8000", "--no-reload"]
