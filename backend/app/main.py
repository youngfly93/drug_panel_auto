"""FastAPI application factory."""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.router import api_router
from app.config import settings
from app.database import Base, engine
from app.dependencies import pwd_context
from app.models import User  # noqa: F401 — ensure models are registered
from app.ws.progress import router as ws_router


class SPAStaticFiles(StaticFiles):
    """Serve Vite assets and fall back to index.html for frontend routes."""

    async def get_response(self, path: str, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            if path in {"docs", "redoc", "openapi.json"} or path.startswith(
                ("api/", "ws/", "docs/", "redoc/")
            ):
                raise
            return await super().get_response("index.html", scope)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup/shutdown events."""
    import logging

    from app.services.runtime_instance_lock import (
        acquire_runtime_instance_lock,
        release_runtime_instance_lock,
    )

    _log = logging.getLogger("reportgen-web")
    instance_lock = acquire_runtime_instance_lock()
    try:
        # Ensure storage directories exist
        for d in [
            settings.upload_dir,
            settings.report_dir,
            settings.preview_dir,
            settings.signature_dir,
            settings.reference_report_dir,
            settings.storage_root / "db",
        ]:
            d.mkdir(parents=True, exist_ok=True)

        # Create tables only after this process owns the runtime lock.
        Base.metadata.create_all(bind=engine)

        if settings.secret_key == "change-me-in-production":
            _log.warning(
                "⚠ SECRET_KEY is using default value — "
                "set RG_WEB_SECRET_KEY for production"
            )
        if settings.default_admin_password == "admin123":
            _log.warning(
                "⚠ Admin password is default 'admin123' — "
                "set RG_WEB_DEFAULT_ADMIN_PASSWORD"
            )

        # Seed default admin if no users exist
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            if db.query(User).count() == 0:
                admin = User(
                    username=settings.default_admin_username,
                    password_hash=pwd_context.hash(settings.default_admin_password),
                    display_name="管理员",
                    role="admin",
                )
                db.add(admin)
                db.commit()
        finally:
            db.close()

        # P0 perf: start a persistent LibreOffice listener so template-render's
        # 2–3 field-refresh calls reuse one warm soffice process instead of cold-
        # starting one each time (~5–8 s saved per call). Non-fatal on failure.
        try:
            from app.services.libreoffice_listener import start_listener, warmup_async
            start_listener()
            warmup_async()
        except Exception as exc:
            _log.warning("LibreOffice listener startup skipped (non-fatal): %s", exc)

        # Recovery runs only after the prior process can no longer own the shared
        # runtime. This prevents a new worker from requeueing work still being
        # completed by a gracefully shutting-down predecessor.
        if settings.recover_interrupted_tasks_on_startup:
            try:
                from app.dependencies import get_bridge
                from app.services.task_recovery import recover_interrupted_tasks

                recovery = recover_interrupted_tasks(bridge=get_bridge())
                if recovery.get("scanned"):
                    _log.warning("Recovered interrupted report tasks: %s", recovery)
            except Exception as exc:
                _log.warning("Task recovery skipped (non-fatal): %s", exc)

        yield
    finally:
        try:
            from app.services.libreoffice_listener import stop_listener
            stop_listener()
        except Exception:
            pass
        try:
            from app.services.generation_queue import shutdown_generation_queue
            shutdown_generation_queue()
        except Exception:
            pass
        release_runtime_instance_lock(instance_lock)


def create_app() -> FastAPI:
    app = FastAPI(
        title="基因组Panel自动化报告系统",
        description="Genomic panel report automation web platform",
        version="0.1.0",
        lifespan=lifespan,
        docs_url="/docs" if settings.docs_enabled else None,
        redoc_url="/redoc" if settings.docs_enabled else None,
        openapi_url="/openapi.json" if settings.docs_enabled else None,
    )

    # CORS — restrict in production via RG_WEB_CORS_ORIGINS env var
    import os
    cors_origins = os.environ.get("RG_WEB_CORS_ORIGINS", "").split(",")
    cors_origins = [o.strip() for o in cors_origins if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins or ["*"],  # default "*" only if env not set
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # API routes
    app.include_router(api_router)

    # WebSocket routes
    app.include_router(ws_router)

    # Serve frontend static files if built
    static_dir = Path(__file__).parent.parent / "static"
    if static_dir.exists():
        app.mount("/", SPAStaticFiles(directory=str(static_dir), html=True), name="static")

    return app


app = create_app()
