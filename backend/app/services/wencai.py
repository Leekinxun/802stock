from __future__ import annotations

import importlib
import math
import os
import re
import time
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_DOWN, ROUND_HALF_UP
from typing import Any, Callable

from app.core.symbols import to_ts_code
from app.schemas.market import (
    WencaiIntersectionResponse,
    WencaiIntersectionStepResult,
    WencaiQueryResponse,
)
from app.services.live_legacy import load_live_realtime_quote
from app.schemas.watchlist import WatchlistCreate
from app.services.local_store import get_local_store

DEFAULT_DELISTED_QUERY = '退市股票'
DEFAULT_DELISTED_SORT_KEY = '退市@退市日期'
DEFAULT_DELISTED_SORT_ORDER = 'asc'
WENCAI_COOKIE_DOMAINS = ('iwencai.com', '10jqka.com.cn')
WENCAI_CODE_PATTERNS = ('股票代码', 'code')
WENCAI_NAME_PATTERNS = ('股票简称', '简称', '股票名称')
WENCAI_BOARD_PATTERNS = ('所属板块', '板块', '市场类型', '证券类型')
WENCAI_PREV_CLOSE_PATTERNS = ('前收盘价', '昨收盘价', '前收', '昨收', '前收价', '昨收价')
WENCAI_PRICE_PATTERNS = ('收盘价', '最新价', '现价', 'close')
WENCAI_LIMIT_UP_PATTERNS = ('当日涨停价', '涨停价')
WENCAI_LIMIT_UP_FIELD = '当日涨停价'
WENCAI_ALMOST_LIMIT_UP_FIELD = '9.95%价格'
WENCAI_ALMOST_LIMIT_UP_RATIO = Decimal('0.0995')
WENCAI_PRICE_TICK = Decimal('0.01')
WencaiProgressCallback = Callable[[int, int, list[WencaiIntersectionStepResult], str], None]
WencaiPrevCloseCache = dict[str, Decimal | None]


def _serialize_value(value: Any) -> Any:
    if value is None:
        return None

    if hasattr(value, 'to_pydatetime'):
        try:
            value = value.to_pydatetime()
        except Exception:
            pass

    if hasattr(value, 'item'):
        try:
            value = value.item()
        except Exception:
            pass

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value

    if isinstance(value, dict):
        return {str(key): _serialize_value(item) for key, item in value.items()}

    if isinstance(value, (list, tuple, set)):
        return [_serialize_value(item) for item in value]

    return value


def _frame_to_payload(frame: Any, *, limit: int) -> tuple[list[str], list[dict[str, Any]]]:
    columns = [str(column) for column in list(getattr(frame, 'columns', []))]
    if not hasattr(frame, 'to_dict'):
        return columns, []

    rows = frame.to_dict(orient='records')
    serialized = [
        {str(key): _serialize_value(value) for key, value in row.items()}
        for row in rows[:limit]
    ]
    return columns, serialized


def _normalize_field_key(value: str) -> str:
    return ''.join(str(value or '').split()).lower()


def _pick_field_value(row: dict[str, Any], patterns: tuple[str, ...]) -> Any | None:
    for key, value in row.items():
        normalized_key = _normalize_field_key(key)
        if any(_normalize_field_key(pattern) in normalized_key for pattern in patterns):
            return value
    return None


def _coerce_decimal(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None

    candidate = value
    if hasattr(candidate, 'item'):
        try:
            candidate = candidate.item()
        except Exception:
            pass

    if isinstance(candidate, (int, float, Decimal)):
        try:
            return Decimal(str(candidate))
        except InvalidOperation:
            return None

    text = str(candidate).strip().replace(',', '')
    if not text or text == '--':
        return None

    matched = re.search(r'-?\d+(?:\.\d+)?', text)
    if not matched:
        return None

    try:
        return Decimal(matched.group(0))
    except InvalidOperation:
        return None


def _extract_ts_code_from_row(row: dict[str, Any]) -> str | None:
    raw_symbol = _pick_field_value(row, WENCAI_CODE_PATTERNS)
    symbol = to_ts_code(str(raw_symbol or '').strip())
    if not symbol or symbol == '--' or '.' not in symbol:
        return None
    return symbol


def _extract_board_text(row: dict[str, Any]) -> str:
    board_value = _pick_field_value(row, WENCAI_BOARD_PATTERNS)
    return ''.join(str(board_value or '').split()).upper()


def _is_risk_warning_stock(row: dict[str, Any]) -> bool:
    name = ''.join(str(_pick_field_value(row, WENCAI_NAME_PATTERNS) or '').upper().split())
    board_text = _extract_board_text(row)
    return (
        name.startswith(('*ST', 'ST', 'S*ST', 'SST'))
        or '风险警示' in board_text
    )


def _infer_limit_up_ratio(row: dict[str, Any]) -> Decimal | None:
    board_text = _extract_board_text(row)
    symbol = _extract_ts_code_from_row(row)

    if '北交所' in board_text or '北京证券交易所' in board_text:
        return Decimal('0.30')
    if '创业板' in board_text or 'CHINEXT' in board_text:
        return Decimal('0.20')
    if '科创板' in board_text or 'STAR' in board_text:
        return Decimal('0.20')

    if symbol:
        digits, exchange = symbol.split('.', 1)
        if exchange == 'BJ':
            return Decimal('0.30')
        if exchange == 'SZ' and digits.startswith(('300', '301')):
            return Decimal('0.20')
        if exchange == 'SH' and digits.startswith('688'):
            return Decimal('0.20')
        if exchange in {'SH', 'SZ'} and _is_risk_warning_stock(row):
            return Decimal('0.05')
        if exchange in {'SH', 'SZ'}:
            return Decimal('0.10')

    if _is_risk_warning_stock(row):
        return Decimal('0.05')
    return None


def _extract_limit_up_reference_price(
    row: dict[str, Any],
    *,
    prev_close_price: Decimal | None = None,
) -> Decimal | None:
    if prev_close_price is not None and prev_close_price > 0:
        return prev_close_price

    for patterns in (WENCAI_PREV_CLOSE_PATTERNS, WENCAI_PRICE_PATTERNS):
        price = _coerce_decimal(_pick_field_value(row, patterns))
        if price is not None and price > 0:
            return price
    return None


def _extract_prev_close_price(row: dict[str, Any]) -> Decimal | None:
    price = _coerce_decimal(_pick_field_value(row, WENCAI_PREV_CLOSE_PATTERNS))
    if price is not None and price > 0:
        return price
    return None


def _fetch_prev_close_price_by_symbol(
    row: dict[str, Any],
    *,
    prev_close_cache: WencaiPrevCloseCache,
) -> Decimal | None:
    prev_close_price = _extract_prev_close_price(row)
    if prev_close_price is not None:
        return prev_close_price

    symbol = _extract_ts_code_from_row(row)
    if not symbol:
        return None

    if symbol in prev_close_cache:
        return prev_close_cache[symbol]

    try:
        quote = load_live_realtime_quote(symbol)
    except Exception:
        prev_close_cache[symbol] = None
        return None

    fetched_prev_close = _coerce_decimal(quote.prev_close)
    prev_close_cache[symbol] = fetched_prev_close if fetched_prev_close is not None and fetched_prev_close > 0 else None
    return prev_close_cache[symbol]


def _compute_limit_up_price(
    row: dict[str, Any],
    *,
    prev_close_cache: WencaiPrevCloseCache,
) -> float | None:
    existing_limit_up = _coerce_decimal(_pick_field_value(row, WENCAI_LIMIT_UP_PATTERNS))
    if existing_limit_up is not None and existing_limit_up > 0:
        return float(existing_limit_up.quantize(WENCAI_PRICE_TICK, rounding=ROUND_HALF_UP))

    prev_close_price = _fetch_prev_close_price_by_symbol(row, prev_close_cache=prev_close_cache)
    base_price = _extract_limit_up_reference_price(row, prev_close_price=prev_close_price)
    limit_up_ratio = _infer_limit_up_ratio(row)
    if base_price is None or limit_up_ratio is None:
        return None

    if _is_risk_warning_stock(row) and limit_up_ratio <= Decimal('0.05') and base_price <= Decimal('0.10'):
        limit_up_price = base_price + WENCAI_PRICE_TICK
    else:
        limit_up_price = (base_price * (Decimal('1') + limit_up_ratio)).quantize(
            WENCAI_PRICE_TICK,
            rounding=ROUND_HALF_UP,
        )
        if limit_up_price <= base_price:
            limit_up_price = (base_price + WENCAI_PRICE_TICK).quantize(
                WENCAI_PRICE_TICK,
                rounding=ROUND_HALF_UP,
            )

    return float(limit_up_price)


def _compute_almost_limit_up_price(
    row: dict[str, Any],
    *,
    prev_close_cache: WencaiPrevCloseCache,
) -> float | None:
    base_price = _fetch_prev_close_price_by_symbol(row, prev_close_cache=prev_close_cache)
    if base_price is None:
        return None

    threshold_price = (base_price * (Decimal('1') + WENCAI_ALMOST_LIMIT_UP_RATIO)).quantize(
        WENCAI_PRICE_TICK,
        rounding=ROUND_DOWN,
    )
    return float(threshold_price)


def _attach_limit_up_prices(
    columns: list[str],
    items: list[dict[str, Any]],
) -> tuple[list[str], list[dict[str, Any]]]:
    next_columns = list(columns)
    if WENCAI_LIMIT_UP_FIELD not in next_columns:
        next_columns.append(WENCAI_LIMIT_UP_FIELD)
    if WENCAI_ALMOST_LIMIT_UP_FIELD not in next_columns:
        next_columns.append(WENCAI_ALMOST_LIMIT_UP_FIELD)

    prev_close_cache: WencaiPrevCloseCache = {}
    next_items: list[dict[str, Any]] = []
    for row in items:
        next_row = dict(row)
        next_row[WENCAI_LIMIT_UP_FIELD] = _compute_limit_up_price(next_row, prev_close_cache=prev_close_cache)
        next_row[WENCAI_ALMOST_LIMIT_UP_FIELD] = _compute_almost_limit_up_price(next_row, prev_close_cache=prev_close_cache)
        next_items.append(next_row)

    return next_columns, next_items


def _extract_watch_candidate(row: dict[str, Any]) -> tuple[str, str] | None:
    raw_symbol = _pick_field_value(row, WENCAI_CODE_PATTERNS)
    raw_name = _pick_field_value(row, WENCAI_NAME_PATTERNS)
    symbol = str(raw_symbol or '').strip()
    display_name = str(raw_name or '').strip()
    if not symbol or not display_name:
        return None

    normalized_symbol = to_ts_code(symbol)
    if not normalized_symbol or normalized_symbol == '--' or display_name == '--':
        return None

    return normalized_symbol, display_name


def _build_intersection_watch_note(queries: list[str]) -> str:
    normalized_queries = [
        f'{index + 1}. {" ".join(query.split())}'
        for index, query in enumerate(queries)
        if query and query.strip()
    ]
    note = f'问财交集导入：{" | ".join(normalized_queries)}'
    return note[:497] + '...' if len(note) > 500 else note


def _build_intersection_payload(
    responses: list[WencaiQueryResponse],
) -> tuple[list[str], list[dict[str, Any]]]:
    row_maps: list[dict[str, tuple[dict[str, Any], str]]] = []
    ordered_symbols: list[str] = []

    for response in responses:
        response_rows: dict[str, tuple[dict[str, Any], str]] = {}
        for row in response.items:
            candidate = _extract_watch_candidate(row)
            if not candidate:
                continue
            symbol, display_name = candidate
            response_rows.setdefault(symbol, (row, display_name))
            if symbol not in ordered_symbols:
                ordered_symbols.append(symbol)
        row_maps.append(response_rows)

    if not row_maps:
        return [], []

    intersection_symbols = [
        symbol
        for symbol in ordered_symbols
        if all(symbol in row_map for row_map in row_maps)
    ]

    items: list[dict[str, Any]] = []
    for symbol in intersection_symbols:
        merged_row: dict[str, Any] = {}
        display_name: str | None = None
        for row_map in row_maps:
            matched = row_map.get(symbol)
            if not matched:
                continue
            row, matched_name = matched
            merged_row.update(row)
            display_name = display_name or matched_name

        if _pick_field_value(merged_row, WENCAI_CODE_PATTERNS) is None:
            merged_row['股票代码'] = symbol
        if display_name and _pick_field_value(merged_row, WENCAI_NAME_PATTERNS) is None:
            merged_row['股票简称'] = display_name

        items.append(merged_row)

    columns: list[str] = []
    seen_columns: set[str] = set()
    for response in responses:
        for column in response.columns:
            if column not in seen_columns:
                columns.append(column)
                seen_columns.add(column)
    for item in items:
        for column in item:
            if column not in seen_columns:
                columns.append(column)
                seen_columns.add(column)

    return columns, items


def _import_intersection_watchlist(rows: list[dict[str, Any]], queries: list[str]) -> tuple[int, int]:
    store = get_local_store()
    existing_symbols = {to_ts_code(item.symbol) for item in store.list_watchlist()}
    note = _build_intersection_watch_note(queries)
    added_count = 0
    existing_count = 0

    for row in rows:
        candidate = _extract_watch_candidate(row)
        if not candidate:
            continue
        symbol, display_name = candidate
        if symbol in existing_symbols:
            existing_count += 1
            continue

        store.add_watchlist_item(
            WatchlistCreate(
                symbol=symbol,
                display_name=display_name,
                sector=None,
                tags=['问财交集'],
                note=note,
            )
        )
        existing_symbols.add(symbol)
        added_count += 1

    return added_count, existing_count


def _cookie_matches_domain(cookie: Any) -> bool:
    domain = str(getattr(cookie, 'domain', '') or '').lstrip('.').lower()
    return any(domain == suffix or domain.endswith(f'.{suffix}') for suffix in WENCAI_COOKIE_DOMAINS)


def _cookiejar_to_header_value(cookie_jar: Any) -> str:
    pairs: list[str] = []
    seen: set[tuple[str, str]] = set()

    for cookie in cookie_jar:
        if not _cookie_matches_domain(cookie):
            continue

        name = str(getattr(cookie, 'name', '') or '').strip()
        value = str(getattr(cookie, 'value', '') or '').strip()
        if not name or not value:
            continue

        key = (name, value)
        if key in seen:
            continue
        seen.add(key)
        pairs.append(f'{name}={value}')

    return '; '.join(pairs)


def _load_wencai_cookie_from_chrome() -> tuple[str | None, str | None]:
    try:
        browser_cookie3 = importlib.import_module('browser_cookie3')
    except ModuleNotFoundError:
        return None, '当前环境未安装 browser-cookie3，无法自动读取 Chrome Cookie。'

    try:
        cookie_jar = browser_cookie3.chrome()
        cookie = _cookiejar_to_header_value(cookie_jar)
    except Exception as exc:
        return None, f'自动读取 Chrome Cookie 失败：{exc}'

    if not cookie:
        return None, '未能从 Chrome 中找到 iwencai / 10jqka 相关 Cookie。'

    return cookie, None


def _query_frame(
    pywencai: Any,
    *,
    query: str,
    sort_key: str | None,
    sort_order: str | None,
    cookie: str,
    limit: int,
    query_type: str,
) -> tuple[Any | None, str | None]:
    try:
        frame = pywencai.get(
            query=query,
            sort_key=sort_key,
            sort_order=sort_order,
            cookie=cookie,
            perpage=max(1, min(limit, 100)),
            query_type=query_type,
            loop=False,
        )
    except Exception as exc:
        return None, str(exc)

    if frame is None:
        return None, 'pywencai 没有返回可用结果。'
    return frame, None


def load_delisted_stocks(limit: int = 50) -> WencaiQueryResponse:
    return run_wencai_query(
        query=DEFAULT_DELISTED_QUERY,
        sort_key=DEFAULT_DELISTED_SORT_KEY,
        sort_order=DEFAULT_DELISTED_SORT_ORDER,
        limit=limit,
    )


def run_wencai_query(
    *,
    query: str,
    sort_key: str | None = None,
    sort_order: str | None = None,
    limit: int = 50,
    query_type: str = 'stock',
) -> WencaiQueryResponse:
    normalized_query = (query or '').strip()
    if not normalized_query:
        return WencaiQueryResponse(
            query='',
            sort_key=sort_key,
            sort_order=sort_order,
            query_type=query_type,
            source='pywencai',
            supported=False,
            columns=[],
            items=[],
            note='缺少问财查询语句。',
        )

    manual_cookie = os.getenv('WENCAI_COOKIE', '').strip()
    auto_cookie: str | None = None
    auto_cookie_note: str | None = None

    def _ensure_auto_cookie() -> tuple[str | None, str | None]:
        nonlocal auto_cookie, auto_cookie_note
        if auto_cookie is None and auto_cookie_note is None:
            auto_cookie, auto_cookie_note = _load_wencai_cookie_from_chrome()
        return auto_cookie, auto_cookie_note

    attempts: list[tuple[str, str]] = []
    if manual_cookie:
        attempts.append(('env', manual_cookie))
    else:
        cookie, cookie_note = _ensure_auto_cookie()
        if cookie:
            attempts.append(('chrome-auto', cookie))
        else:
            return WencaiQueryResponse(
                query=normalized_query,
                sort_key=sort_key,
                sort_order=sort_order,
                query_type=query_type,
                source='pywencai',
                supported=False,
                columns=[],
                items=[],
                note=cookie_note or '未配置 WENCAI_COOKIE，且无法自动读取 Chrome Cookie。',
            )

    try:
        pywencai = importlib.import_module('pywencai')
    except ModuleNotFoundError:
        return WencaiQueryResponse(
            query=normalized_query,
            sort_key=sort_key,
            sort_order=sort_order,
            query_type=query_type,
            source='pywencai',
            supported=False,
            columns=[],
            items=[],
            note='当前环境未安装 pywencai，请先安装 backend/requirements.txt 中的依赖。',
        )

    last_error: str | None = None
    note_on_success: str | None = None
    frame = None
    for source_name, cookie in list(attempts):
        frame, error = _query_frame(
            pywencai,
            query=normalized_query,
            sort_key=sort_key,
            sort_order=sort_order,
            cookie=cookie,
            limit=limit,
            query_type=query_type,
        )
        if frame is not None:
            if source_name == 'chrome-auto':
                note_on_success = '已自动从 Chrome 读取问财 Cookie。'
            break
        last_error = error

    if frame is None and manual_cookie:
        cookie, cookie_note = _ensure_auto_cookie()
        if cookie and cookie != manual_cookie:
            frame, error = _query_frame(
                pywencai,
                query=normalized_query,
                sort_key=sort_key,
                sort_order=sort_order,
                cookie=cookie,
                limit=limit,
                query_type=query_type,
            )
            if frame is not None:
                note_on_success = '检测到本地 WENCAI_COOKIE 失效，已自动回退到 Chrome 登录态。'
            else:
                last_error = error or last_error
        elif cookie_note:
            last_error = last_error or cookie_note

    if frame is None:
        return WencaiQueryResponse(
            query=normalized_query,
            sort_key=sort_key,
            sort_order=sort_order,
            query_type=query_type,
            source='pywencai',
            supported=False,
            columns=[],
            items=[],
            note=f'pywencai 请求失败：{last_error}' if last_error else 'pywencai 没有返回可用结果。',
        )

    columns, items = _frame_to_payload(frame, limit=limit)
    if query_type == 'stock':
        columns, items = _attach_limit_up_prices(columns, items)
    return WencaiQueryResponse(
        query=normalized_query,
        sort_key=sort_key,
        sort_order=sort_order,
        query_type=query_type,
        source='pywencai',
        supported=True,
        columns=columns,
        items=items,
        note=note_on_success or (None if items else 'pywencai 已请求成功，但当前查询结果为空。'),
    )


def run_wencai_intersection(
    *,
    queries: list[str],
    sort_key: str | None = None,
    sort_order: str | None = None,
    limit: int = 50,
    query_type: str = 'stock',
    interval_seconds: int = 90,
    import_to_watchlist: bool = True,
    progress_callback: WencaiProgressCallback | None = None,
) -> WencaiIntersectionResponse:
    normalized_queries = [str(query or '').strip() for query in queries if str(query or '').strip()]
    if not normalized_queries:
        return WencaiIntersectionResponse(
            query='',
            sort_key=sort_key,
            sort_order=sort_order,
            query_type=query_type,
            source='pywencai-intersection',
            supported=False,
            columns=[],
            items=[],
            requested_query_count=0,
            executed_query_count=0,
            intersection_count=0,
            watchlist_added_count=0,
            watchlist_existing_count=0,
            step_results=[],
            note='至少需要提供 1 条问财语句。',
        )

    responses: list[WencaiQueryResponse] = []
    step_results: list[WencaiIntersectionStepResult] = []
    total_queries = len(normalized_queries)

    for index, query in enumerate(normalized_queries):
        if progress_callback is not None:
            progress_callback(
                index,
                total_queries,
                step_results,
                f'开始执行第 {index + 1} / {total_queries} 条问财语句。',
            )
        result = run_wencai_query(
            query=query,
            sort_key=sort_key,
            sort_order=sort_order,
            limit=limit,
            query_type=query_type,
        )
        responses.append(result)
        step_results.append(
            WencaiIntersectionStepResult(
                query=query,
                supported=result.supported,
                item_count=len(result.items),
                note=result.note,
            )
        )
        if progress_callback is not None:
            progress_callback(
                index + 1,
                total_queries,
                step_results,
                f'第 {index + 1} / {total_queries} 条执行完成，返回 {len(result.items)} 条结果。',
            )

        if not result.supported:
            return WencaiIntersectionResponse(
                query=' ∩ '.join(normalized_queries),
                sort_key=sort_key,
                sort_order=sort_order,
                query_type=query_type,
                source='pywencai-intersection',
                supported=False,
                columns=[],
                items=[],
                requested_query_count=len(normalized_queries),
                executed_query_count=index + 1,
                intersection_count=0,
                watchlist_added_count=0,
                watchlist_existing_count=0,
                step_results=step_results,
                note=f'第 {index + 1} 次问财查询失败：{result.note or "未返回可用结果。"}',
            )

        if index < len(normalized_queries) - 1 and interval_seconds > 0:
            if progress_callback is not None:
                progress_callback(
                    index + 1,
                    total_queries,
                    step_results,
                    f'等待 {interval_seconds} 秒后执行第 {index + 2} / {total_queries} 条问财语句。',
                )
            time.sleep(interval_seconds)

    columns, items = _build_intersection_payload(responses)
    intersection_count = len(items)
    added_count = 0
    existing_count = 0
    if import_to_watchlist and items:
        added_count, existing_count = _import_intersection_watchlist(items, normalized_queries)

    if intersection_count:
        note = (
            f'已完成 {len(normalized_queries)} 次问财查询，交集 {intersection_count} 只；'
            f'观察池新增 {added_count} 只，已存在 {existing_count} 只。'
        )
    else:
        note = f'已完成 {len(normalized_queries)} 次问财查询，但当前交集为空。'

    return WencaiIntersectionResponse(
        query=' ∩ '.join(normalized_queries),
        sort_key=sort_key,
        sort_order=sort_order,
        query_type=query_type,
        source='pywencai-intersection',
        supported=True,
        columns=columns,
        items=items,
        requested_query_count=len(normalized_queries),
        executed_query_count=len(normalized_queries),
        intersection_count=intersection_count,
        watchlist_added_count=added_count,
        watchlist_existing_count=existing_count,
        step_results=step_results,
        note=note,
    )
