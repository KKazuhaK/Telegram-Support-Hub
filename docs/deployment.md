# 部署说明

本项目支持两种部署形态：

```text
形态 A（推荐用于一键起步）
  Docker Compose 自带 MariaDB 11.4 + Redis 7 + 业务程序

形态 B（推荐用于正式生产）
  宿主机安装 MariaDB 11.4、Redis 7
  Docker 只跑 backend-api、worker-send、worker-account、worker-beat
```

镜像仓库：GitHub Container Registry（GHCR）。

## 1. GitHub 自动构建镜像

仓库推送到 `main` 或 `master` 后，GitHub Actions 会自动：

1. 安装 Python 依赖。
2. 执行语法编译和 smoke tests。
3. 构建 Docker 镜像。
4. 推送到 GHCR。

当前仓库的默认镜像名：

```text
ghcr.io/kkazuhak/telegram-support-hub:latest
```

同时会生成：

```text
ghcr.io/kkazuhak/telegram-support-hub:<branch>
ghcr.io/kkazuhak/telegram-support-hub:sha-<commit>
ghcr.io/kkazuhak/telegram-support-hub:<tag>
```

如果 GitHub Package 默认是私有，需要在 GitHub 页面里手动改成公开：

```text
GitHub 仓库页面
  -> Packages
  -> telegram-support-hub
  -> Package settings
  -> Change visibility
  -> Public
```

公开后，服务器可以直接拉：

```bash
docker pull ghcr.io/kkazuhak/telegram-support-hub:latest
```

如果保持私有，需要在服务器登录 GHCR：

```bash
echo <GITHUB_TOKEN> | docker login ghcr.io -u <GITHUB_USERNAME> --password-stdin
```

Token 至少需要 `read:packages` 权限。

## 2. 服务器目录

服务器建议目录：

```text
/opt/tg-support-hub/
  docker-compose.prod.yml
  .env
  data/
    mariadb/
    redis/
    sessions/
    uploads/
    logs/
```

创建目录：

```bash
sudo mkdir -p /opt/tg-support-hub/data/{mariadb,redis,sessions,uploads,logs}
sudo chown -R $USER:$USER /opt/tg-support-hub
```

## 3. 服务器环境变量

复制 `.env.example` 为 `.env`，至少修改：

```env
APP_ENV=production
APP_SECRET=replace-with-random-secret
APP_JWT_SECRET=replace-with-random-jwt-secret
AUTO_CREATE_TABLES=true

# 形态 A：使用 compose 自带 MariaDB 时填 mariadb
# 形态 B：使用宿主机 MariaDB 时填 host.docker.internal
MYSQL_HOST=mariadb
MYSQL_PORT=3306
MYSQL_DATABASE=tg_support_hub
MYSQL_USER=tg_support
MYSQL_PASSWORD=replace-with-strong-password
MYSQL_ROOT_PASSWORD=replace-with-strong-root-password

REDIS_HOST=redis
REDIS_PORT=6379
REDIS_PASSWORD=replace-with-strong-password
REDIS_DB=0

TELEGRAM_API_ID=
TELEGRAM_API_HASH=

SESSION_DIR=/app/data/sessions
UPLOAD_DIR=/app/data/uploads
LOG_DIR=/app/data/logs
```

`APP_SECRET` 用于加密代理密码，上线后不要随意更换。更换后旧代理密码无法解密。
`APP_JWT_SECRET` 用于签发客服登录 token，更换后已签发的 token 全部失效。

## 4. MariaDB 11.4

### 形态 A：Docker Compose 自带

无需手动安装，`docker-compose.prod.yml` 会自动起 `mariadb:11.4` 并按 `.env` 创建数据库和用户。数据持久化到 `./data/mariadb`。

### 形态 B：宿主机安装

安装 MariaDB 11.4 LTS（Ubuntu 22.04/24.04）：

```bash
# 来源：https://mariadb.org/download/?t=repo-config
curl -LsSO https://r.mariadb.com/downloads/mariadb_repo_setup
chmod +x mariadb_repo_setup
sudo ./mariadb_repo_setup --mariadb-server-version=11.4
sudo apt update
sudo apt install -y mariadb-server mariadb-client
sudo mariadb-secure-installation
```

建库（注意排序规则）：

```sql
CREATE DATABASE tg_support_hub
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_uca1400_ai_ci;

CREATE USER 'tg_support'@'%' IDENTIFIED BY 'replace-with-strong-password';
GRANT ALL PRIVILEGES ON tg_support_hub.* TO 'tg_support'@'%';
FLUSH PRIVILEGES;
```

安全建议：

1. MariaDB 不开放公网端口，`bind-address = 127.0.0.1` 或仅允许内网。
2. 生产环境每日 `mariadb-dump` 备份，至少保留 7 天。
3. 升级时优先升级到下一个 patch 版本（如 11.4.x → 11.4.y），跨大版本升级前做完整备份。

## 5. Redis 7

### 形态 A：Docker Compose 自带

无需手动安装，按 `.env` 中 `REDIS_PASSWORD` 启动并启用密码。数据持久化到 `./data/redis`。

### 形态 B：宿主机安装

安装：

```bash
sudo apt install -y redis-server
```

修改 `/etc/redis/redis.conf`：

```conf
bind 127.0.0.1
requirepass replace-with-strong-password
```

重启：`sudo systemctl restart redis-server`。

## 6. 启动服务

在服务器 `/opt/tg-support-hub/` 下放置：

```text
docker-compose.prod.yml
.env
```

拉取并启动：

```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

查看状态：

```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f backend-api
```

访问：

```text
http://服务器IP:8000/health
http://服务器IP:8000/docs
```

首次启动后建议立即创建管理员账号（见接口 `POST /api/auth/bootstrap-admin`）。

## 7. 数据库迁移

项目使用 Alembic 管理 schema 变更。

首次部署：

```bash
docker compose -f docker-compose.prod.yml exec backend-api \
  alembic -c backend/alembic.ini upgrade head
```

后续升级版本时，重复上面命令即可。`AUTO_CREATE_TABLES=true` 仅适合开发环境快速建表，生产建议设为 `false` 并依赖 Alembic。

## 8. 更新版本

代码 push 到 GitHub，Actions 构建完成后，在服务器执行：

```bash
cd /opt/tg-support-hub
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
docker compose -f docker-compose.prod.yml exec backend-api \
  alembic -c backend/alembic.ini upgrade head
```

## 9. 回滚版本

使用某个 commit 镜像：

```bash
APP_IMAGE=ghcr.io/kkazuhak/telegram-support-hub:sha-xxxxxxx \
  docker compose -f docker-compose.prod.yml up -d
```

也可以把 `.env` 里加上：

```env
APP_IMAGE=ghcr.io/kkazuhak/telegram-support-hub:sha-xxxxxxx
```

然后执行：

```bash
docker compose -f docker-compose.prod.yml up -d
```

回滚时如果对应镜像的 schema 比当前 schema 旧，需要先用 `alembic downgrade <revision>` 回滚到对应版本。

## 10. 备份

每日 cron 建议：

```bash
0 3 * * * docker compose -f /opt/tg-support-hub/docker-compose.prod.yml exec -T mariadb \
  mariadb-dump -u root -p"$MYSQL_ROOT_PASSWORD" tg_support_hub \
  | gzip > /opt/tg-support-hub/backup/db-$(date +\%F).sql.gz

10 3 * * * tar czf /opt/tg-support-hub/backup/sessions-$(date +\%F).tgz \
  /opt/tg-support-hub/data/sessions
```

session 文件包含登录凭据，备份目录建议加密存放。
