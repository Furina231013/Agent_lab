"""Keep the entrypoint thin so it mostly wires parts together.

That makes startup easier to scan and avoids hiding business logic in the
first file new readers usually open.
"""

from fastapi import FastAPI

from app.api import ask, health, ingest, search
from app.config import settings


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version="0.5.4",
        docs_url="/docs",
        redoc_url="/redoc",
    )
    application.include_router(health.router, prefix="/api")
    application.include_router(ingest.router, prefix="/api")
    application.include_router(search.router, prefix="/api")
    application.include_router(ask.router, prefix="/api")
    return application


app = create_app()
