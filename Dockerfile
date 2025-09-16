FROM python:3.11-slim

# 使用官方推荐方式安装 uv
ADD https://astral.sh/uv/install.sh /install.sh
RUN chmod +x /install.sh && /install.sh && rm /install.sh

# 验证uv安装
RUN uv --version

# 设置工作目录
WORKDIR /app

# 创建非root用户并提前配置缓存目录
RUN mkdir -p /root/.cache/uv

# 从CI构建的dist目录复制所有文件
COPY dist/ .

# 安装依赖（仍使用root用户确保权限）
RUN uv sync --no-dev --no-cache && uv cache prune

# 暴露应用端口
EXPOSE 60000

# 设置环境变量，指定uv缓存目录和用户主目录
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:/app/bin:$PATH" \
    HOME="/root" \
    UV_CACHE_DIR="/root/.cache/uv"

# 启动命令
CMD ["uv", "run", "main.py", "--workers", "4"]
