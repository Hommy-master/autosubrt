FROM python:3.11-slim

# 内置北京时区：slim 镜像不含 tzdata，仅设 TZ 环境变量无法解析，需一并安装并写入时区文件
ENV TZ=Asia/Shanghai
RUN DEBIAN_FRONTEND=noninteractive apt-get update \
    && apt-get install -y --no-install-recommends tzdata \
    && ln -snf /usr/share/zoneinfo/$TZ /etc/localtime \
    && echo $TZ > /etc/timezone \
    && rm -rf /var/lib/apt/lists/*

# 使用pip安装uv
RUN pip install --no-cache-dir uv

# 验证uv安装
RUN uv --version

# 设置工作目录
WORKDIR /app

# 从CI构建的dist目录复制所有文件
COPY dist/ .

# 安装依赖（仍使用root用户确保权限）；--no-dev 只装运行依赖，容器里不需要 pytest
RUN uv sync --no-dev --no-cache && uv cache prune

# 校验运行依赖已完整进入镜像：缺依赖在构建阶段就报错，而不是等容器启动才发现
RUN /app/.venv/bin/python -c "import main"

# 暴露应用端口
EXPOSE 30000

# 设置环境变量：PATH 指向镜像内虚拟环境，PYTHONUNBUFFERED 保证日志实时输出
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    HOME="/root"

# 启动命令：直接用镜像内 .venv 的 python，不走 uv。
# uv run 会隐式执行一次 uv sync，且默认带上 dev 组去 PyPI 补装 pytest 等依赖，
# 于是每次启动都要联网下载（国内网络下会长时间卡住），详见 README 7.1
CMD ["python", "main.py", "--workers", "4"]
