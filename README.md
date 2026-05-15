# TG Support Hub

Telegram 多账号客服管理系统，当前处于架构落地初期。

## 技术栈

- 后端 API：Python + FastAPI
- Telegram Worker：Python + Telethon
- 数据库：MySQL 8
- 队列 / 缓存 / 锁：Redis
- 任务执行：Celery
- 部署：MySQL / Redis 安装在宿主机，业务程序使用 Docker 运行

## 当前已实现

- FastAPI 项目骨架
- MySQL SQLAlchemy 模型
- 账号 session ZIP 导入接口
- 账号分组接口
- 网络代理管理和检测接口
- 客服账号分组权限接口
- 客户导入接口
- 消息模板接口
- 群发任务和消息队列记录接口
- Celery worker 骨架
- Dockerfile / docker-compose.yml

## 开发流程

项目后续遵循 TDD：

```text
先写 unittest
再实现功能
最后跑测试和编译检查
```

运行测试：

```bash
python -m unittest discover -s tests -p "test_*.py"
```

运行语法检查：

```bash
python -m compileall backend
```

## 本地启动

先复制配置：

```bash
copy .env.example .env
```

修改 `.env` 中的 MySQL 和 Redis 配置，然后安装依赖：

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

启动 API：

```bash
uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

打开：

```text
http://localhost:8000/docs
```

## Docker 启动业务程序

MySQL 8 和 Redis 7 按架构文档建议安装在宿主机，Docker 只跑业务程序：

```bash
docker compose up -d --build
```

如果 Docker 容器需要连接宿主机 MySQL / Redis，`.env` 默认使用：

```env
MYSQL_HOST=host.docker.internal
REDIS_HOST=host.docker.internal
```

## GitHub 自动构建镜像

推送到 GitHub 的 `main` 或 `master` 分支后，Actions 会自动构建并推送 Docker 镜像到 GHCR：

```text
ghcr.io/kkazuhak/telegram-support-hub:latest
```

服务器部署可使用：

```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

详细步骤见 [deployment.md](docs/deployment.md)。

## 数据目录

运行时数据建议放在：

```text
data/
  sessions/
  uploads/
  logs/
```

这些目录不会提交到 Git。

## 当前边界

当前版本已经把业务模型、接口边界和 worker 入口接好，但还没有启用真实 Telegram 发送。

后续需要继续实现：

- Telethon session 校验
- 账号登录状态同步
- 使用账号绑定代理连接 Telegram
- 真实消息发送
- 回复监听
- 群发调度锁和发送间隔精细化
- 登录鉴权和角色权限中间件
