from pydantic import BaseModel

from app.schemas.event import EventFeedItem
from app.schemas.market import LonghubangItem, MarketAnomalyItem
from app.schemas.watchlist import WatchlistItem


class SignalItem(BaseModel):
    id: int
    snapshot_id: int
    watchlist_id: int
    symbol: str
    display_name: str
    score: float
    confidence: float
    action: str
    summary: str
    reasons: list[str]
    created_at: str


class SignalResponse(BaseModel):
    items: list[SignalItem]


class SignalSyncResponse(BaseModel):
    snapshot_id: int
    watchlist_count: int
    signal_count: int
    notes: list[str]
    top_signals: list[SignalItem]


class PersistedMarketSnapshot(BaseModel):
    hot_sectors: list[dict]
    anomalies: list[MarketAnomalyItem]
    longhubang: list[LonghubangItem]
    events: list[EventFeedItem]


class WatchlistSignalView(BaseModel):
    watchlist: WatchlistItem
    latest_signal: SignalItem | None = None
