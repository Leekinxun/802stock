from fastapi import APIRouter

from app.api.routes import dashboard, events, health, market, platform, signals, watchlist

api_router = APIRouter()
api_router.include_router(health.router, tags=['health'])
api_router.include_router(dashboard.router, prefix='/dashboard', tags=['dashboard'])
api_router.include_router(events.router, prefix='/events', tags=['events'])
api_router.include_router(market.router, prefix='/market', tags=['market'])
api_router.include_router(platform.router, prefix='/platform', tags=['platform'])
api_router.include_router(watchlist.router, prefix='/watchlist', tags=['watchlist'])
api_router.include_router(signals.router, prefix='/signals', tags=['signals'])
