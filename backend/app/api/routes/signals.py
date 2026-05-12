from fastapi import APIRouter, Query

from app.schemas.signal import SignalResponse, SignalSyncResponse
from app.services.signal_engine import list_latest_signals, sync_signals

router = APIRouter()


@router.get('', response_model=SignalResponse)
def list_signals(limit: int = Query(default=20, ge=1, le=100)) -> SignalResponse:
    return SignalResponse(items=list_latest_signals(limit=limit))


@router.post('/sync', response_model=SignalSyncResponse)
def sync_signal_snapshot() -> SignalSyncResponse:
    return sync_signals()
