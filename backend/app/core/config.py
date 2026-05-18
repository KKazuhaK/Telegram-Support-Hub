import os
from functools import cached_property
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy.engine import URL

load_dotenv()


def _int_env(key: str, default: int) -> int:
    try:
        return int(os.getenv(key, str(default)))
    except ValueError:
        return default


class Settings:
    app_env: str = os.getenv("APP_ENV", "development")
    app_name: str = os.getenv("APP_NAME", "TG Support Hub")
    app_secret: str = os.getenv("APP_SECRET", "dev-secret")
    app_jwt_secret: str = os.getenv("APP_JWT_SECRET", os.getenv("APP_SECRET", "dev-secret"))
    app_jwt_ttl_minutes: int = _int_env("APP_JWT_TTL_MINUTES", 720)
    auto_create_tables: bool = os.getenv("AUTO_CREATE_TABLES", "true").lower() == "true"
    # On startup, ALTER TABLE ADD COLUMN for any column declared in models
    # but missing in the live DB. Default tracks AUTO_CREATE_TABLES so an
    # operator who opts into auto schema gets the additive migrations too.
    auto_migrate_columns: bool = os.getenv(
        "AUTO_MIGRATE_COLUMNS",
        os.getenv("AUTO_CREATE_TABLES", "true"),
    ).lower() == "true"

    mysql_host: str = os.getenv("MYSQL_HOST", "127.0.0.1")
    mysql_port: int = _int_env("MYSQL_PORT", 3306)
    mysql_database: str = os.getenv("MYSQL_DATABASE", "tg_support_hub")
    mysql_user: str = os.getenv("MYSQL_USER", "root")
    mysql_password: str = os.getenv("MYSQL_PASSWORD", "")

    redis_host: str = os.getenv("REDIS_HOST", "127.0.0.1")
    redis_port: int = _int_env("REDIS_PORT", 6379)
    redis_password: str = os.getenv("REDIS_PASSWORD", "")
    redis_db: int = _int_env("REDIS_DB", 0)

    telegram_api_id: str = os.getenv("TELEGRAM_API_ID", "")
    telegram_api_hash: str = os.getenv("TELEGRAM_API_HASH", "")

    session_dir: Path = Path(os.getenv("SESSION_DIR", "./data/sessions"))
    upload_dir: Path = Path(os.getenv("UPLOAD_DIR", "./data/uploads"))
    log_dir: Path = Path(os.getenv("LOG_DIR", "./data/logs"))

    dispatch_batch_size: int = _int_env("DISPATCH_BATCH_SIZE", 50)
    dispatch_lock_ttl_padding: int = _int_env("DISPATCH_LOCK_TTL_PADDING", 30)
    max_failed_attempts: int = _int_env("MAX_FAILED_ATTEMPTS", 3)
    # Comma-separated origins permitted by the CORS middleware.
    # Production deployments MUST pin this to actual frontend hosts —
    # pairing "*" with allow_credentials=True is rejected by browsers
    # and degrades to echoing arbitrary Origin headers (security risk).
    # Empty value disables CORS entirely (safest for same-origin deploys).
    cors_allow_origins: str = os.getenv("CORS_ALLOW_ORIGINS", "")

    @cached_property
    def database_url(self) -> URL:
        return URL.create(
            "mysql+pymysql",
            username=self.mysql_user,
            password=self.mysql_password,
            host=self.mysql_host,
            port=self.mysql_port,
            database=self.mysql_database,
            query={"charset": "utf8mb4"},
        )

    @cached_property
    def redis_url(self) -> str:
        auth = f":{self.redis_password}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{self.redis_db}"

    def ensure_directories(self) -> None:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.log_dir.mkdir(parents=True, exist_ok=True)


settings = Settings()
