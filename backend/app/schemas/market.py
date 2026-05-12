from pydantic import BaseModel, Field

from app.schemas.dashboard import HotSectorItem


class HotSectorResponse(BaseModel):
    items: list[HotSectorItem]


class MarketAnomalyItem(BaseModel):
    title: str
    stock_code: str | None = None
    stock_name: str | None = None
    anomaly_type: str
    summary: str
    timestamp: str
    source: str


class MarketAnomalyResponse(BaseModel):
    items: list[MarketAnomalyItem]


class LonghubangItem(BaseModel):
    stock_code: str
    stock_name: str
    reason: str
    net_amount: str
    buy_total: str
    sell_total: str
    timestamp: str
    source: str


class LonghubangResponse(BaseModel):
    items: list[LonghubangItem]


class SectorStockItem(BaseModel):
    code: str
    name: str
    exchange: str
    sector: str
    concepts: list[str]
    source: str


class SectorStockResponse(BaseModel):
    sector_code: str
    items: list[SectorStockItem]


class IntradayTrendPoint(BaseModel):
    time: str
    open: float
    high: float
    low: float
    close: float
    volume: float | None = None
    amount: float | None = None


class IntradayTrendResponse(BaseModel):
    symbol: str
    source: str
    supported: bool
    points: list[IntradayTrendPoint]
    open_price: float | None = None
    latest_price: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    change_pct: float | None = None
    note: str | None = None


class RealtimeOrderFlow(BaseModel):
    buy_large: float | None = None
    buy_small: float | None = None
    sell_large: float | None = None
    sell_small: float | None = None


class RealtimeQuoteResponse(BaseModel):
    symbol: str
    market_symbol: str
    source: str
    supported: bool
    name: str | None = None
    price: float | None = None
    prev_close: float | None = None
    open_price: float | None = None
    high_price: float | None = None
    low_price: float | None = None
    change: float | None = None
    change_pct: float | None = None
    volume_hands: float | None = None
    amount_wan: float | None = None
    quote_time: str | None = None
    bid_price_1: float | None = None
    bid_volume_1: float | None = None
    ask_price_1: float | None = None
    ask_volume_1: float | None = None
    order_flow: RealtimeOrderFlow | None = None
    note: str | None = None


class WencaiQueryRequest(BaseModel):
    query: str
    sort_key: str | None = None
    sort_order: str | None = None
    limit: int = 50
    query_type: str = 'stock'


class WencaiQueryResponse(BaseModel):
    query: str
    sort_key: str | None = None
    sort_order: str | None = None
    query_type: str = 'stock'
    source: str
    supported: bool
    columns: list[str]
    items: list[dict]
    note: str | None = None


class WencaiIntersectionStepResult(BaseModel):
    query: str
    supported: bool
    item_count: int
    note: str | None = None


class WencaiIntersectionRequest(BaseModel):
    queries: list[str] = Field(default_factory=list, min_length=1, max_length=12)
    sort_key: str | None = None
    sort_order: str | None = None
    limit: int = 50
    query_type: str = 'stock'
    interval_seconds: int = Field(default=90, ge=0, le=600)
    import_to_watchlist: bool = True


class WencaiIntersectionResponse(BaseModel):
    query: str
    sort_key: str | None = None
    sort_order: str | None = None
    query_type: str = 'stock'
    source: str
    supported: bool
    columns: list[str]
    items: list[dict]
    requested_query_count: int
    executed_query_count: int
    intersection_count: int
    watchlist_added_count: int = 0
    watchlist_existing_count: int = 0
    step_results: list[WencaiIntersectionStepResult] = Field(default_factory=list)
    note: str | None = None


class WencaiIntersectionJobCreateResponse(BaseModel):
    job_id: str
    status: str
    created_at: str
    requested_query_count: int
    poll_after_seconds: int = 5
    note: str | None = None


class WencaiIntersectionJobResponse(BaseModel):
    job_id: str
    status: str
    created_at: str
    updated_at: str
    started_at: str | None = None
    completed_at: str | None = None
    requested_query_count: int
    executed_query_count: int = 0
    step_results: list[WencaiIntersectionStepResult] = Field(default_factory=list)
    note: str | None = None
    result: WencaiIntersectionResponse | None = None


class MarketSnapshotResponse(BaseModel):
    hot_sectors: list[HotSectorItem]
    anomalies: list[MarketAnomalyItem]
    longhubang: list[LonghubangItem]
