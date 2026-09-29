"""FastAPI application factory."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.errors import register_error_handlers
from app.api.routers import health
from app.api.routers.users import router as user_router
from app.database.conf.alch_conf import Base, engine


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Sudoku 42",
        version="0.1.0",
        # The interactive docs describe the API to anyone who can reach it.
        # Harmless in development, noise in production.
        docs_url=None if settings.is_production else "/api/docs",
        openapi_url=None if settings.is_production else "/api/openapi.json",
    )

    Base.metadata.create_all(bind=engine)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.frontend_origin],
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type"],
    )

    register_error_handlers(app)
    app.include_router(health.router, prefix="/api")
    app.include_router(user_router, prefix="/api") 

    return app


app = create_app()
