from fastapi import APIRouter, HTTPException, Query

from app.schemas.market import (
    HotSectorResponse,
    IntradayTrendResponse,
    LonghubangResponse,
    MarketAnomalyResponse,
    MarketSentimentResponse,
    MarketSnapshotResponse,
    RealtimeQuoteResponse,
    SectorStockResponse,
    WencaiIntersectionJobCreateResponse,
    WencaiIntersectionJobResponse,
    WencaiIntersectionRequest,
    WencaiIntersectionResponse,
    WencaiQueryRequest,
    WencaiQueryResponse,
)
from app.services.live_legacy import (
    load_live_intraday_trend,
    load_live_anomalies,
    load_live_hot_sectors,
    load_live_longhubang,
    load_live_realtime_quote,
    load_live_sector_stocks,
)
from app.services.market_sentiment import load_market_sentiment
from app.services.wencai import load_delisted_stocks
from app.services.wencai import run_wencai_intersection
from app.services.wencai import run_wencai_query
from app.services.wencai_jobs import create_wencai_intersection_job, get_wencai_intersection_job

router = APIRouter()


@router.get('/hot-sectors', response_model=HotSectorResponse)
def get_hot_sectors(limit: int = Query(default=6, ge=1, le=20)) -> HotSectorResponse:
    return HotSectorResponse(items=load_live_hot_sectors(limit=limit))


@router.get('/anomalies', response_model=MarketAnomalyResponse)
def get_anomalies(limit: int = Query(default=8, ge=1, le=30)) -> MarketAnomalyResponse:
    return MarketAnomalyResponse(items=load_live_anomalies(limit=limit))


@router.get('/longhubang', response_model=LonghubangResponse)
def get_longhubang(limit: int = Query(default=8, ge=1, le=30)) -> LonghubangResponse:
    return LonghubangResponse(items=load_live_longhubang(limit=limit))


@router.get('/sentiment', response_model=MarketSentimentResponse)
def get_market_sentiment(limit: int = Query(default=5, ge=1, le=20)) -> MarketSentimentResponse:
    return load_market_sentiment(limit=limit)


@router.get('/sector-stocks/{sector_code}', response_model=SectorStockResponse)
def get_sector_stocks(
    sector_code: str,
    limit: int = Query(default=20, ge=1, le=100),
) -> SectorStockResponse:
    return SectorStockResponse(sector_code=sector_code, items=load_live_sector_stocks(sector_code=sector_code, limit=limit))


@router.get('/intraday/{symbol}', response_model=IntradayTrendResponse)
def get_intraday_trend(symbol: str) -> IntradayTrendResponse:
    return load_live_intraday_trend(symbol=symbol)


@router.get('/realtime/{symbol}', response_model=RealtimeQuoteResponse)
def get_realtime_quote(symbol: str) -> RealtimeQuoteResponse:
    return load_live_realtime_quote(symbol=symbol)


@router.get('/delisted-stocks', response_model=WencaiQueryResponse)
def get_delisted_stocks(limit: int = Query(default=50, ge=1, le=100)) -> WencaiQueryResponse:
    return load_delisted_stocks(limit=limit)


@router.post('/wencai-query', response_model=WencaiQueryResponse)
def post_wencai_query(payload: WencaiQueryRequest) -> WencaiQueryResponse:
    return run_wencai_query(
        query=payload.query,
        sort_key=payload.sort_key,
        sort_order=payload.sort_order,
        limit=max(1, min(payload.limit, 100)),
        query_type=payload.query_type or 'stock',
    )


@router.post('/wencai-intersection', response_model=WencaiIntersectionResponse)
def post_wencai_intersection(payload: WencaiIntersectionRequest) -> WencaiIntersectionResponse:
    return run_wencai_intersection(
        queries=payload.queries,
        sort_key=payload.sort_key,
        sort_order=payload.sort_order,
        limit=max(1, min(payload.limit, 100)),
        query_type=payload.query_type or 'stock',
        interval_seconds=max(0, min(payload.interval_seconds, 600)),
        import_to_watchlist=payload.import_to_watchlist,
    )


@router.post('/wencai-intersection/jobs', response_model=WencaiIntersectionJobCreateResponse, status_code=202)
def create_wencai_intersection_background_job(payload: WencaiIntersectionRequest) -> WencaiIntersectionJobCreateResponse:
    return create_wencai_intersection_job(payload)


@router.get('/wencai-intersection/jobs/{job_id}', response_model=WencaiIntersectionJobResponse)
def get_wencai_intersection_background_job(job_id: str) -> WencaiIntersectionJobResponse:
    job = get_wencai_intersection_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail='wencai job not found')
    return job


@router.get('/snapshot', response_model=MarketSnapshotResponse)
def get_market_snapshot(
    sector_limit: int = Query(default=6, ge=1, le=20),
    anomaly_limit: int = Query(default=8, ge=1, le=30),
    longhubang_limit: int = Query(default=8, ge=1, le=30),
) -> MarketSnapshotResponse:
    return MarketSnapshotResponse(
        hot_sectors=load_live_hot_sectors(limit=sector_limit),
        anomalies=load_live_anomalies(limit=anomaly_limit),
        longhubang=load_live_longhubang(limit=longhubang_limit),
    )
