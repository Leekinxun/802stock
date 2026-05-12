from fastapi import APIRouter, Query

from app.schemas.event import EventFeedResponse
from app.services.platform_summary import build_event_feed

router = APIRouter()


@router.get('', response_model=EventFeedResponse)
def list_events(limit: int = Query(default=9, ge=1, le=30)) -> EventFeedResponse:
    return build_event_feed(limit=limit)
