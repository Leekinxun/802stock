from fastapi import APIRouter, Query

from app.schemas.dashboard import DashboardPayload
from app.services.platform_summary import build_dashboard_payload

router = APIRouter()


@router.get('', response_model=DashboardPayload)
def get_dashboard(
    event_limit: int = Query(default=9, ge=1, le=30),
    sector_limit: int = Query(default=6, ge=1, le=20),
) -> DashboardPayload:
    return build_dashboard_payload(event_limit=event_limit, sector_limit=sector_limit)
