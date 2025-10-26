from fastapi import FastAPI

from backend.core.config import settings
from backend.core.observability import init_observability
from backend.core.observability.health import router as health_router
from backend.apps.inbox.api import router as upload_router
from backend.apps.inbox.api_read import router as read_router
from backend.apps.inbox.api_ops import router as ops_router
from backend.apps.inbox.api_read_model import router as read_model_router


def create_app() -> FastAPI:
    init_observability(enable_metrics=settings.enable_metrics)

    app = FastAPI(title="0Admin-NEXT Backend")

    # Routers
    app.include_router(health_router)
    app.include_router(upload_router)
    app.include_router(read_router)
    app.include_router(ops_router)
    app.include_router(read_model_router)

    return app


# ASGI app instance
app = create_app()
