# 部署说明

本项目推荐：

```text
宿主机安装：MySQL 8、Redis 7
Docker 运行：backend-api、worker-send、worker-account、worker-beat
镜像仓库：GitHub Container Registry GHCR
```

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
    sessions/
    uploads/
    logs/
```

创建目录：

```bash
sudo mkdir -p /opt/tg-support-hub/data/{sessions,uploads,logs}
sudo chown -R $USER:$USER /opt/tg-support-hub
```

## 3. 服务器环境变量

复制 `.env.example` 为 `.env`，至少修改：

```env
APP_ENV=production
APP_SECRET=replace-with-random-secret
AUTO_CREATE_TABLES=true

MYSQL_HOST=host.docker.internal
MYSQL_PORT=3306
MYSQL_DATABASE=tg_support_hub
MYSQL_USER=tg_support
MYSQL_PASSWORD=replace-with-strong-password

REDIS_HOST=host.docker.internal
REDIS_PORT=6379
REDIS_PASSWORD=replace-with-strong-password
REDIS_DB=0

TELEGRAM_API_ID=
TELEGRAM_API_HASH=

SESSION_DIR=/app/data/sessions
UPLOAD_DIR=/app/data/uploads
LOG_DIR=/app/data/logs
```

`APP_SECRET` 用于加密代理密码，上线后不要随意更换。更换后，旧代理密码无法解密。

## 4. MySQL

示例建库：

```sql
CREATE DATABASE tg_support_hub CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'tg_support'@'%' IDENTIFIED BY 'replace-with-strong-password';
GRANT ALL PRIVILEGES ON tg_support_hub.* TO 'tg_support'@'%';
FLUSH PRIVILEGES;
```

安全建议：

1. MySQL 不开放公网端口。
2. 只允许本机、Docker 网桥或内网访问。
3. 生产环境定期备份。

## 5. Redis

安全建议：

1. Redis 不开放公网端口。
2. 设置 `requirepass`。
3. 只监听 `127.0.0.1` 或内网地址。

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

## 7. 更新版本

代码 push 到 GitHub，Actions 构建完成后，在服务器执行：

```bash
cd /opt/tg-support-hub
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

## 8. 回滚版本

使用某个 commit 镜像：

```bash
APP_IMAGE=ghcr.io/kkazuhak/telegram-support-hub:sha-xxxxxxx docker compose -f docker-compose.prod.yml up -d
```

也可以把 `.env` 里加上：

```env
APP_IMAGE=ghcr.io/kkazuhak/telegram-support-hub:sha-xxxxxxx
```

然后执行：

```bash
docker compose -f docker-compose.prod.yml up -d
```
