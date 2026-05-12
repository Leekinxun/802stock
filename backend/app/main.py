from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.router import api_router
from app.core.config import PROJECT_ROOT, settings
from app.services.wencai_jobs import recover_wencai_jobs


FRONTEND_DIST = PROJECT_ROOT / 'frontend' / 'dist'


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description='基于 STOCK 旧项目演进的量化研究与可视化平台后端。',
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allow_origins,
        allow_credentials=True,
        allow_methods=['*'],
        allow_headers=['*'],
    )

    app.include_router(api_router, prefix=settings.api_prefix)

    if FRONTEND_DIST.exists():
        app.mount('/', StaticFiles(directory=FRONTEND_DIST, html=True), name='frontend')

    @app.on_event('startup')
    def _startup_recover_jobs() -> None:
        recover_wencai_jobs()

    return app


app = create_app()
