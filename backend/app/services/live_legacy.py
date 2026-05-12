from __future__ import annotations

import re
import time
from datetime import datetime
from types import MethodType
from typing import Any, Callable, TypeVar

import requests

from app.legacy.collectors.event_collectors.announcement_collector import AnnouncementCollector
from app.legacy.collectors.event_collectors.company_news_collector import CompanyNewsCollector
from app.legacy.collectors.event_collectors.zt_radar_collector import ZTRadarCollector
from app.legacy.datasources.tencent_quote_source import TencentQuoteSource
from app.legacy.datasources.tonghuashun_source import TonghuashunSource
from app.schemas.dashboard import HotSectorItem
from app.schemas.event import EventFeedItem
from app.schemas.market import (
    IntradayTrendResponse,
    LonghubangItem,
    MarketAnomalyItem,
    RealtimeOrderFlow,
    RealtimeQuoteResponse,
    SectorStockItem,
)

T = TypeVar('T')

REQUEST_TIMEOUT_SECONDS = 4
CACHE_TTL_SECONDS = 60
_CACHE: dict[str, tuple[float, Any]] = {}


def _cached(key: str, loader: Callable[[], T], ttl: int = CACHE_TTL_SECONDS) -> T:
    now = time.time()
    cached_value = _CACHE.get(key)
    if cached_value and cached_value[0] > now:
        return cached_value[1]

    value = loader()
    _CACHE[key] = (now + ttl, value)
    return value


def _truncate(text: str, max_chars: int = 90) -> str:
    normalized = re.sub(r'\s+', ' ', text or '').strip()
    if len(normalized) <= max_chars:
        return normalized
    return f'{normalized[: max_chars - 1]}…'


def _format_timestamp(value: Any) -> tuple[str, datetime]:
    if isinstance(value, datetime):
        dt_value = value
    else:
        dt_value = datetime.now()
    return dt_value.strftime('%Y-%m-%d %H:%M'), dt_value


def _today_label() -> str:
    return datetime.now().strftime('%Y-%m-%d')


def _infer_sentiment(text: str) -> str:
    positive_keywords = ('涨停', '利好', '增长', '超预期', '中标', '回购', '增持', '龙头')
    negative_keywords = ('跌停', '利空', '亏损', '减持', '处罚', '下滑', '问询', '风险')

    if any(keyword in text for keyword in positive_keywords):
        return 'positive'
    if any(keyword in text for keyword in negative_keywords):
        return 'negative'
    return 'neutral'


def _make_fast_tonghuashun_source() -> Any:
    source = TonghuashunSource()

    def _patched_get(self: Any, path: str, base_url: str | None = None) -> str:
        url = (base_url or self.BASE_URL) + path
        headers = {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
            'Referer': base_url or self.BASE_URL,
        }
        response = requests.get(url, headers=headers, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding
        return response.text

    source._get = MethodType(_patched_get, source)
    return source


def _load_tonghuashun_events(limit: int) -> list[Any]:
    collector_classes = (CompanyNewsCollector, AnnouncementCollector, ZTRadarCollector)
    events: list[Any] = []

    for collector_class in collector_classes:
        try:
            collector = collector_class(timeout=REQUEST_TIMEOUT_SECONDS, max_retries=0)
            collector.data_source = _make_fast_tonghuashun_source()
            events.extend(collector.run(limit=limit))
        except Exception:
            continue

    events.sort(key=lambda item: getattr(item, 'publish_time', datetime.min), reverse=True)
    return events[:limit]


def _load_tonghuashun_hot_sectors(limit: int) -> list[HotSectorItem]:
    source = _make_fast_tonghuashun_source()
    items = source.get_hot_sectors()

    sectors: list[HotSectorItem] = []
    for item in items[:limit]:
        name = item.get('name') or item.get('sector_name')
        if not name:
            continue
        thesis = item.get('event') or item.get('capital_flow') or '来自同花顺热点板块抓取。'
        sectors.append(
            HotSectorItem(
                name=name,
                change_pct=str(item.get('change_pct') or '--'),
                leader=item.get('leader') or item.get('leader_stock') or '--',
                thesis=thesis,
                code=item.get('code'),
                source='tonghuashun',
            )
        )

    return sectors


def load_live_hot_sectors(limit: int = 6) -> list[HotSectorItem]:
    def _loader() -> list[HotSectorItem]:
        try:
            sectors = _load_tonghuashun_hot_sectors(limit)
            if sectors:
                return sectors
        except Exception:
            pass

        return []

    return _cached(f'hot-sectors:{limit}', _loader)


def load_live_events(limit: int = 9) -> list[EventFeedItem]:
    def _loader() -> list[EventFeedItem]:
        collector_limit = max(3, min(limit, 6))
        items: list[EventFeedItem] = []

        for event in _load_tonghuashun_events(limit=collector_limit):
            title = getattr(event, 'title', '').strip()
            content = getattr(event, 'content', '').strip()
            if not title:
                continue
            timestamp_label, _ = _format_timestamp(getattr(event, 'publish_time', None))
            items.append(
                EventFeedItem(
                    title=title,
                    source=getattr(event, 'source', 'legacy-collector'),
                    timestamp=timestamp_label,
                    sentiment=_infer_sentiment(f'{title} {content}'),
                    summary=_truncate(content or title),
                )
            )

        if not items:
            return []

        return items[:limit]

    return _cached(f'events:{limit}', _loader)


def _load_tonghuashun_anomalies(limit: int) -> list[MarketAnomalyItem]:
    collector = ZTRadarCollector(timeout=REQUEST_TIMEOUT_SECONDS, max_retries=0)
    collector.data_source = _make_fast_tonghuashun_source()
    events = collector.run(limit=limit)

    anomalies: list[MarketAnomalyItem] = []
    for event in events[:limit]:
        timestamp, _ = _format_timestamp(getattr(event, 'publish_time', None))
        title = getattr(event, 'title', '').strip()
        anomalies.append(
            MarketAnomalyItem(
                title=title,
                stock_code=None,
                stock_name=None,
                anomaly_type='涨停雷达',
                summary=_truncate(getattr(event, 'content', '') or title),
                timestamp=timestamp,
                source=getattr(event, 'source', 'tonghuashun_zt_radar'),
            )
        )
    return anomalies


def load_live_anomalies(limit: int = 8) -> list[MarketAnomalyItem]:
    def _loader() -> list[MarketAnomalyItem]:
        try:
            items = _load_tonghuashun_anomalies(limit)
            if items:
                return items
        except Exception:
            pass

        return []

    return _cached(f'anomalies:{limit}', _loader)


def _load_tonghuashun_longhubang(limit: int) -> list[LonghubangItem]:
    source = _make_fast_tonghuashun_source()
    items = source.get_longhubang()

    rows: list[LonghubangItem] = []
    for item in items[:limit]:
        timestamp = str(item.get('date') or _today_label())
        rows.append(
            LonghubangItem(
                stock_code=str(item.get('code') or ''),
                stock_name=str(item.get('name') or ''),
                reason=str(item.get('reason') or item.get('change_pct') or '--'),
                net_amount=str(item.get('net_buy') or '--'),
                buy_total=str(item.get('amount') or item.get('buy_total') or '--'),
                sell_total=str(item.get('sell_total') or '--'),
                timestamp=timestamp,
                source='tonghuashun',
            )
        )
    return rows


def load_live_longhubang(limit: int = 8) -> list[LonghubangItem]:
    def _loader() -> list[LonghubangItem]:
        try:
            items = _load_tonghuashun_longhubang(limit)
            if items:
                return items
        except Exception:
            pass

        return []

    return _cached(f'longhubang:{limit}', _loader)


def load_live_sector_stocks(sector_code: str, limit: int = 20) -> list[SectorStockItem]:
    def _loader() -> list[SectorStockItem]:
        return []

    return _cached(f'sector-stocks:{sector_code}:{limit}', _loader)


def load_live_intraday_trend(symbol: str) -> IntradayTrendResponse:
    normalized_symbol = symbol.strip()
    if not normalized_symbol:
        return IntradayTrendResponse(
            symbol='',
            source='unavailable',
            supported=False,
            points=[],
            note='缺少股票代码，无法获取当日走势。',
        )

    def _loader() -> IntradayTrendResponse:
        return IntradayTrendResponse(
            symbol=normalized_symbol,
            source='disabled',
            supported=False,
            points=[],
            open_price=None,
            latest_price=None,
            day_high=None,
            day_low=None,
            change_pct=None,
            note='当前版本已移除 StockAPI 分钟线依赖，当日走势暂不提供。',
        )

    return _cached(f'intraday:{normalized_symbol}', _loader, ttl=30)


def load_live_realtime_quote(symbol: str) -> RealtimeQuoteResponse:
    normalized_symbol = symbol.strip()
    if not normalized_symbol:
        return RealtimeQuoteResponse(
            symbol='',
            market_symbol='',
            source='unavailable',
            supported=False,
            note='缺少股票代码，无法获取实时行情。',
        )

    def _loader() -> RealtimeQuoteResponse:
        tencent_source = TencentQuoteSource()
        quote = tencent_source.get_realtime_quote(normalized_symbol)
        if quote.get('supported'):
            return RealtimeQuoteResponse(
                symbol=str(quote.get('symbol') or normalized_symbol),
                market_symbol=str(quote.get('market_symbol') or normalized_symbol),
                source='tencent-qt',
                supported=True,
                name=quote.get('name'),
                price=quote.get('price'),
                prev_close=quote.get('prev_close'),
                open_price=quote.get('open_price'),
                high_price=quote.get('high_price'),
                low_price=quote.get('low_price'),
                change=quote.get('change'),
                change_pct=quote.get('change_pct'),
                volume_hands=quote.get('volume_hands'),
                amount_wan=quote.get('amount_wan'),
                quote_time=quote.get('quote_time'),
                bid_price_1=quote.get('bid_price_1'),
                bid_volume_1=quote.get('bid_volume_1'),
                ask_price_1=quote.get('ask_price_1'),
                ask_volume_1=quote.get('ask_volume_1'),
                order_flow=RealtimeOrderFlow(
                    buy_large=quote.get('buy_large'),
                    buy_small=quote.get('buy_small'),
                    sell_large=quote.get('sell_large'),
                    sell_small=quote.get('sell_small'),
                ),
                note=quote.get('note'),
            )

        return RealtimeQuoteResponse(
            symbol=normalized_symbol,
            market_symbol=quote.get('market_symbol') or normalized_symbol,
            source='tencent-qt',
            supported=False,
            note=quote.get('note') or '腾讯实时行情暂时不可用，当前未启用其他回退数据源。',
        )

    return _cached(f'realtime-quote:{normalized_symbol}', _loader, ttl=10)
