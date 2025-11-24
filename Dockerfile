FROM python:3.11-alpine

# 1. 首先安装系统依赖
RUN apk add --no-cache \
    gcc \
    g++ \
    musl-dev \
    libffi-dev \
    openssl-dev \
    cargo \
    fontconfig \
    ttf-dejavu

# 2. 安装uv
RUN pip install --no-cache-dir uv

# 验证uv安装
RUN uv --version

# 设置工作目录
WORKDIR /app

# 创建缓存目录
RUN mkdir -p /root/.cache/uv

# 复制项目文件
COPY dist/ .

# 3. 安装字体工具和目录
RUN mkdir -p /usr/share/fonts/truetype

# 4. 同步依赖（启用详细日志）
RUN uv sync --no-dev --no-cache --verbose
RUN uv cache prune

# 复制字体文件
COPY fonts/ /usr/share/fonts/truetype/

# 更新字体缓存
RUN fc-cache -f -v

# 暴露端口
EXPOSE 30000

# 环境变量
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:/app/bin:$PATH" \
    HOME="/root" \
    UV_CACHE_DIR="/root/.cache/uv"

# 启动命令
CMD ["uv", "run", "main.py", "--workers", "4"]