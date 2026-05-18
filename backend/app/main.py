from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.app.api.router import api_router
from backend.app.api.routes import ws as ws_routes
from backend.app.core.config import settings
from backend.app.core.database import create_db_and_tables


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    if settings.auto_create_tables:
        create_db_and_tables()
    yield


def create_app() -> FastAPI:
    app = FastAPI(title=settings.app_name, lifespan=lifespan)

    # CORS: pin to operator-configured origins. Empty CORS_ALLOW_ORIGINS
    # = no middleware (same-origin only). Wildcard "*" is allowed but
    # forces allow_credentials=False because the browser rejects the
    # pair anyway; using "*" + credentials would silently devolve to
    # echoing arbitrary Origin headers.
    raw = settings.cors_allow_origins.strip()
    if raw:
        origins = [o.strip() for o in raw.split(",") if o.strip()]
        with_credentials = origins != ["*"]
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=with_credentials,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "app": settings.app_name, "env": settings.app_env}

    app.include_router(api_router, prefix="/api")
    # WebSocket also mounted at /ws/* directly (matches the frontend's
    # `ws://host/ws/replies?token=...` URL and nginx's `/ws/` proxy
    # block). Without this it sits at /api/ws/replies and the frontend's
    # short URL 404s into a 403 WS upgrade rejection.
    app.include_router(ws_routes.router, prefix="/ws")
    return app


app = create_app()
