from celery import Celery
from celery.schedules import crontab

from backend.app.core.config import settings

celery_app = Celery("tg_support_hub", broker=settings.redis_url, backend=settings.redis_url)

celery_app.conf.imports = (
    "backend.app.workers.account_tasks",
    "backend.app.workers.send_tasks",
    "backend.app.workers.execute_operation",
)

celery_app.conf.task_routes = {
    "backend.app.workers.send_tasks.*": {"queue": "send"},
    "backend.app.workers.account_tasks.*": {"queue": "account"},
    "backend.app.workers.execute_operation.*": {"queue": "send"},
}

celery_app.conf.timezone = "UTC"

celery_app.conf.beat_schedule = {
    "proxy-health-check-every-10-minutes": {
        "task": "backend.app.workers.account_tasks.check_all_proxies",
        "schedule": crontab(minute="*/10"),
    },
    "session-validation-every-15-minutes": {
        "task": "backend.app.workers.account_tasks.validate_all_sessions",
        "schedule": crontab(minute="*/15"),
    },
    "dispatch-send-queue-every-minute": {
        "task": "backend.app.workers.send_tasks.dispatch_send_queue",
        "schedule": crontab(minute="*"),
    },
    "reset-daily-quota-at-midnight-utc": {
        "task": "backend.app.workers.send_tasks.reset_daily_quota",
        "schedule": crontab(minute="0", hour="0"),
    },
}

celery_app.autodiscover_tasks(["backend.app.workers"])
