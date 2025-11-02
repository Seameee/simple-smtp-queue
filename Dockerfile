FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用程序代码
COPY . .

# 创建必要的目录
RUN mkdir -p /app/data /app/logs

# 创建非root用户
RUN groupadd -r smtpqueue && useradd -r -g smtpqueue smtpqueue
RUN chown -R smtpqueue:smtpqueue /app
USER smtpqueue

# 暴露端口
EXPOSE 8025

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8025/health')" || exit 1

# 启动应用程序
CMD ["python", "-m", "app.main"]
