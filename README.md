# TG Support Hub

Telegram 多账号客服管理系统。

## 技术栈

- 后端 API：Python 3.12 + FastAPI
- Telegram Worker：Python + Telethon
- 数据库：MariaDB 11.4 LTS
- 队列 / 缓存 / 锁：Redis 7
- 任务执行：Celery（send / account 队列 + beat）
- 鉴权：JWT（PyJWT）+ bcrypt 密码哈希
- 部署：Docker Compose（自带 MariaDB + Redis，或对接宿主机服务）

## 已实现

后端：

- FastAPI 项目骨架 + lifespan
- SQLAlchemy 2 模型 + Alembic 迁移骨架
- TG 账号 ZIP 导入、账号分组管理、账号代理绑定 + 切换日志
- 网络代理 CRUD + TCP 健康检测
- 客服 + 角色 + 账号分组权限矩阵
- 登录 / `bootstrap-admin` / JWT / `me`
- 客户导入 + 去重 + 分配（轮询 + 单账号上限）
- 好友同步任务（基于 Telethon）+ `friend_broadcast`
- 消息模板
- 群发任务（`customer_broadcast` / `friend_broadcast`）+ 暂停/继续/取消
- 群发调度：Redis 锁、日额度、静默时段、随机间隔、重试到 `failed_permanent`
- 真实 Telegram 发送 + session 校验 + 回复监听 worker
- 审计日志：登录、账号导入、代理绑定、群发任务、客户分配等关键操作
- Beat 调度：代理检测、session 校验、队列分发、每日额度重置

测试：

- `python -m unittest discover -s tests`，目前 42 用例全部通过
- 覆盖：调度、密码 + JWT、客户分配、权限、send/listen worker、auth API

## 开发流程（TDD）

```text
1. 在 tests/ 写 unittest
2. 在 backend/ 写实现
3. python -m unittest discover -s tests -p "test_*.py"
4. python -m compileall backend
```

## 本地启动

```bash
copy .env.example .env
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

uvicorn backend.app.main:app --reload --host 0.0.0.0 --port 8000
```

打开 `http://localhost:8000/docs`。

首次启动后，先创建管理员：

```bash
curl -X POST http://localhost:8000/api/auth/bootstrap-admin \
  -H "Content-Type: application/json" \
  -d '{"username":"root","password":"yourstrongpassword"}'
```

## Docker 一键起步

`docker-compose.yml` 自带 MariaDB 11.4 和 Redis 7：

```bash
docker compose up -d --build
```

需要先把 `.env` 中 `MYSQL_HOST=mariadb`、`REDIS_HOST=redis`（默认即如此）。

如果想连宿主机的 MariaDB / Redis，把 host 改回 `host.docker.internal`，并停掉 compose 中的 `mariadb` / `redis` 服务。

## 数据库迁移

```bash
docker compose exec backend-api alembic -c backend/alembic.ini upgrade head
```

开发环境也可设 `AUTO_CREATE_TABLES=true` 走 `Base.metadata.create_all`，生产建议关掉走 Alembic。

## 服务清单（compose）

| 服务 | 作用 |
| --- | --- |
| `mariadb` | MariaDB 11.4 LTS，持久化到 `./data/mariadb` |
| `redis` | Redis 7，持久化到 `./data/redis` |
| `backend-api` | FastAPI HTTP 服务（端口 8000） |
| `worker-send` | Celery worker，处理 `send` 队列：群发调度 + 真实发送 |
| `worker-account` | Celery worker，处理 `account` 队列：代理检测 / session 校验 / 好友同步 |
| `worker-listen` | 常驻 Telethon 客户端，监听所有启用账号的回复 |
| `worker-beat` | Celery beat，按 cron 触发周期任务 |

## GitHub 自动构建

push 到 `main` 或 `master` 后 Actions 构建并推送：

```text
ghcr.io/kkazuhak/telegram-support-hub:latest
```

详细部署见 [deployment.md](docs/deployment.md)。

## 数据目录

```text
data/
  mariadb/   # MariaDB 数据
  redis/     # Redis 数据
  sessions/  # TG session 文件
  uploads/   # 上传文件
  logs/      # 运行日志
```

均不入 git。

## 前端

`frontend/` 是 Vue 3 + Vite + Element Plus 的管理后台。

```bash
cd frontend
npm install
npm run dev          # 本地开发，默认 5173，自动代理 /api 和 /ws 到 8000
npm run build        # 输出到 frontend/dist
```

页面：登录 / 总览 / TG 账号 / 账号分组 / 网络代理 / 客户管理 / 消息模板 / 群发任务 / 回复管理（含 WebSocket 实时） / 客服中心 / 审计日志。

Docker 启动后访问 `http://localhost:8080`。

## 当前边界

- 真实 Telegram 发送依赖 `TELEGRAM_API_ID` / `TELEGRAM_API_HASH`，未配置时 worker 会 no-op
- listen worker 当前监听所有 active 账号，规模化后建议按账号分组分实例部署
- 群发的 `group_member_notice` 任务类型尚未做（合规要求复杂，暂留位）
- 前端 chunk 体积偏大（1MB+），后续可按路由进一步拆 manualChunks
