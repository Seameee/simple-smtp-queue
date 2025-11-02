# Simple SMTP Queue Proxy

一个极简的SMTP发件服务器中转项目，支持队列发件、速率限制和失败重试功能。

## 功能特性

- ✅ **SMTP代理中转**: 将现有SMTP服务器中转至本地端口
- ✅ **队列发件**: 支持邮件队列管理，异步发送
- ✅ **速率限制**: 可配置每秒发件频率或间隔时间
- ✅ **失败重试**: 自动重试发送失败的邮件
- ✅ **监控接口**: 提供健康检查和统计信息
- ✅ **Docker支持**: 完整的容器化部署方案
- ✅ **GitHub Actions**: 自动化构建和发布

## 快速开始

### 使用 Docker Compose

1. 克隆项目：
```bash
git clone https://github.com/your-username/simple-smtp-queue.git
cd simple-smtp-queue
```

2. 配置环境变量：
```bash
cp .env.example .env
# 编辑 .env 文件，设置你的SMTP服务器信息
```

3. 启动服务：
```bash
docker-compose up -d
```

### 直接运行

1. 安装依赖：
```bash
pip install -r requirements.txt
```

2. 配置环境变量：
```bash
export SMTP_QUEUE_SMTP_HOST=smtp.example.com
export SMTP_QUEUE_SMTP_PORT=587
export SMTP_QUEUE_SMTP_USERNAME=your-username
export SMTP_QUEUE_SMTP_PASSWORD=your-password
```

3. 运行应用：
```bash
python -m app.main
```

## 配置说明

### 环境变量

| 变量名 | 默认值 | 说明 |
|--------|--------|------|
| `SMTP_QUEUE_LOG_LEVEL` | `INFO` | 日志级别 |
| `SMTP_QUEUE_PROXY_HOST` | `0.0.0.0` | 代理服务器监听地址 |
| `SMTP_QUEUE_PROXY_PORT` | `8025` | 代理服务器端口 |
| `SMTP_QUEUE_REDIS_HOST` | `localhost` | Redis主机地址 |
| `SMTP_QUEUE_REDIS_PORT` | `6379` | Redis端口 |
| `SMTP_QUEUE_SMTP_HOST` | - | 目标SMTP服务器地址 |
| `SMTP_QUEUE_SMTP_PORT` | `587` | 目标SMTP服务器端口 |
| `SMTP_QUEUE_SMTP_USERNAME` | - | SMTP用户名 |
| `SMTP_QUEUE_SMTP_PASSWORD` | - | SMTP密码 |
| `SMTP_QUEUE_RATE_LIMIT` | `10` | 速率限制（邮件数） |
| `SMTP_QUEUE_RATE_WINDOW` | `60` | 速率窗口（秒），与`SMTP_QUEUE_RATE_LIMIT`配合使用，表示在多少秒内允许发送指定数量的邮件 |
| `SMTP_QUEUE_MAX_RETRIES` | `3` | 最大重试次数 |
| `SMTP_QUEUE_RETRY_DELAY` | `60` | 重试延迟（秒） |

### 使用方式

配置你的邮件客户端使用SMTP代理服务器：

- **SMTP服务器**: `localhost` (或你的服务器IP)
- **端口**: `8025`
- **认证**: 与目标SMTP服务器相同的认证信息

## API接口

### 健康检查
```
GET /health
```

### 统计信息
```
GET /stats
```

### 队列状态
```
GET /queue
```

## 开发

### 项目结构
```
simple-smtp-queue/
├── app/                    # 应用代码
│   ├── __init__.py
│   ├── main.py            # 主应用程序
│   ├── config.py          # 配置管理
│   ├── smtp_proxy.py      # SMTP代理服务器
│   ├── queue_manager.py   # 队列管理器
│   ├── email_sender.py    # 邮件发送器
│   ├── rate_limiter.py    # 速率限制器
│   ├── monitoring.py      # 监控接口
│   └── models.py          # 数据模型
├── tests/                  # 测试用例
├── Dockerfile             # Docker构建文件
├── docker-compose.yml     # Docker编排文件
├── requirements.txt       # Python依赖
└── README.md             # 项目文档
```

### 运行测试
```bash
pytest tests/
```

## 部署

### Docker镜像
```bash
# 构建镜像
docker build -t smtp-queue .

# 运行容器
docker run -d \
  -p 8025:8025 \
  -e SMTP_QUEUE_SMTP_HOST=smtp.example.com \
  -e SMTP_QUEUE_SMTP_USERNAME=your-username \
  -e SMTP_QUEUE_SMTP_PASSWORD=your-password \
  smtp-queue
```

### GitHub Packages
每次推送到main分支时，会自动构建并发布Docker镜像到GitHub Packages：

```bash
docker pull ghcr.io/your-username/simple-smtp-queue:latest
```

## 许可证

MIT License

## 贡献

欢迎提交Issue和Pull Request！
