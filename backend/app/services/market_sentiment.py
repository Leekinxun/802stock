from __future__ import annotations

import math
import time
from datetime import date, datetime, timedelta
from typing import Any

import requests

from app.schemas.market import MarketSentimentResponse
from app.services.local_store import get_local_store

EASTMONEY_MARKET_LIST_URL = 'https://push2.eastmoney.com/api/qt/clist/get'
EASTMONEY_MARKET_FILTER = 'm:0+t:6,m:0+t:80,m:1+t:2,m:1+t:23,m:0+t:81+s:2048'
REQUEST_TIMEOUT_SECONDS = 4
REQUEST_PAGE_SIZE = 100
REQUEST_RETRY_ATTEMPTS = 3
REQUEST_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}
REQUEST_RETRY_BACKOFF_SECONDS = 0.6
INTER_PAGE_DELAY_SECONDS = 0.12
DEFAULT_KEEP_DAYS = 5


def _previous_weekday(value: date) -> date:
    previous = value - timedelta(days=1)
    while previous.weekday() >= 5:
        previous -= timedelta(days=1)
    return previous


def _resolve_effective_trade_date(now: datetime | None = None) -> date:
    current = now or datetime.now()
    current_date = current.date()

    if current_date.weekday() >= 5:
        return _previous_weekday(current_date)

    if current.hour < 9:
        return _previous_weekday(current_date)

    return current_date


def _iter_quote_rows() -> list[dict[str, Any]]:
    headers = {
        'User-Agent': 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36', #'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
        'Accept': 'application/json,text/plain,*/*',
        'Referer': 'https://quote.eastmoney.com/center/gridlist.html',
    }

    page = 1
    page_size = REQUEST_PAGE_SIZE
    expected_total = 0
    rows: list[dict[str, Any]] = []
    seen_symbols: set[str] = set()
    max_pages = 200
    total_pages = 1

    while page <= max_pages:
        payload: dict[str, Any] | None = None
        last_error: Exception | None = None
        for attempt in range(1, REQUEST_RETRY_ATTEMPTS + 1):
            try:
                response = requests.get(
                    EASTMONEY_MARKET_LIST_URL,
                    params={
                        'pn': page,
                        'pz': page_size,
                        'po': 1,
                        'np': 1,
                        'fltt': 2,
                        'invt': 2,
                        'fid': 'f3',
                        'fs': EASTMONEY_MARKET_FILTER,
                        'fields': 'f12,f14,f3',
                    },
                    headers=headers,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
                if response.status_code in REQUEST_RETRYABLE_STATUS_CODES:
                    raise requests.HTTPError(
                        f'HTTP {response.status_code} for pn={page}',
                        response=response,
                    )

                response.raise_for_status()
                payload = response.json()
                break
            except Exception as exc:
                last_error = exc
                if attempt >= REQUEST_RETRY_ATTEMPTS:
                    raise RuntimeError(f'东方财富行情第 {page} 页抓取失败：{exc}') from exc
                time.sleep(REQUEST_RETRY_BACKOFF_SECONDS * attempt)

        if payload is None:
            raise RuntimeError(f'东方财富行情第 {page} 页抓取失败：{last_error}')

        data = payload.get('data') or {}
        diff = data.get('diff') or []
        if isinstance(diff, dict):
            page_rows = [item for item in diff.values() if isinstance(item, dict)]
        else:
            page_rows = [item for item in diff if isinstance(item, dict)]

        if page == 1:
            expected_total = int(data.get('total') or len(page_rows))
            effective_page_size = max(1, len(page_rows))
            total_pages = max(1, math.ceil(expected_total / effective_page_size))
            total_pages = min(total_pages, max_pages)

        if not page_rows:
            break

        new_rows = 0
        for item in page_rows:
            symbol = str(item.get('f12') or '').strip()
            if symbol and symbol not in seen_symbols:
                seen_symbols.add(symbol)
                rows.append(item)
                new_rows += 1

        if new_rows == 0:
            break

        if expected_total and len(rows) >= expected_total:
            break
        if page >= total_pages:
            break

        page += 1
        time.sleep(INTER_PAGE_DELAY_SECONDS)

    return rows


def _to_float(value: Any) -> float | None:
    if value is None or value == '':
        return None

    if isinstance(value, (int, float)):
        return float(value)

    try:
        return float(str(value).replace('%', '').replace(',', '').strip())
    except (TypeError, ValueError):
        return None


def _fetch_live_market_sentiment() -> tuple[int, int, float]:
    rows = _iter_quote_rows()
    if not rows:
        raise RuntimeError('东方财富返回了空的市场列表。')

    rise_count = 0
    total_count = 0
    for row in rows:
        symbol = str(row.get('f12') or '').strip()
        if not symbol:
            continue

        total_count += 1
        change_pct = _to_float(row.get('f3'))
        if change_pct is not None and change_pct > 0:
            rise_count += 1

    if total_count <= 0:
        raise RuntimeError('未能统计出有效的市场总家数。')

    return rise_count, total_count, rise_count / total_count


def load_market_sentiment(limit: int = DEFAULT_KEEP_DAYS) -> MarketSentimentResponse:
    store = get_local_store()
    effective_trade_date = _resolve_effective_trade_date().isoformat()

    try:
        rise_count, total_count, ratio = _fetch_live_market_sentiment()
        note = '按上涨家数 ÷ 市场总家数计算；周末或开盘前会沿用前一个交易日日期。'
        store.upsert_market_sentiment_point(
            trade_date=effective_trade_date,
            rise_count=rise_count,
            total_count=total_count,
            ratio=ratio,
            source='eastmoney',
            note=note,
            keep_latest=max(1, limit),
        )
        rows = store.list_market_sentiment_points(limit=max(1, limit))
        points = [
            {key: row[key] for key in ('trade_date', 'rise_count', 'total_count', 'ratio', 'source', 'note')}
            for row in reversed(rows)
        ]
        return MarketSentimentResponse(
            points=points,
            supported=True,
            source='eastmoney',
            latest_trade_date=points[-1]['trade_date'] if points else None,
            note=note,
        )
    except Exception as exc:
        rows = store.list_market_sentiment_points(limit=max(1, limit))
        points = [
            {key: row[key] for key in ('trade_date', 'rise_count', 'total_count', 'ratio', 'source', 'note')}
            for row in reversed(rows)
        ]
        if points:
            return MarketSentimentResponse(
                points=points,
                supported=True,
                source='local-store',
                latest_trade_date=points[-1]['trade_date'],
                note=f'实时抓取失败，已回退到本地最近记录：{exc}',
            )

        return MarketSentimentResponse(
            points=[],
            supported=False,
            source='unavailable',
            latest_trade_date=None,
            note=f'暂时无法获取市场情绪踩点数据：{exc}',
        )
