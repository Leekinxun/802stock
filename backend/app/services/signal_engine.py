from __future__ import annotations

from typing import Any

from app.core.symbols import symbol_aliases
from app.schemas.signal import PersistedMarketSnapshot, SignalItem, SignalSyncResponse
from app.schemas.watchlist import WatchlistItem
from app.services.live_legacy import (
    load_live_anomalies,
    load_live_events,
    load_live_hot_sectors,
    load_live_longhubang,
)
from app.services.local_store import get_local_store


def _match_text(needle: str, haystack: str) -> bool:
    return bool(needle) and needle.lower() in haystack.lower()


def _match_symbol_text(aliases: set[str], haystack: str) -> bool:
    text = haystack.lower()
    return any(alias.lower() in text for alias in aliases if alias)


def _build_snapshot() -> PersistedMarketSnapshot:
    return PersistedMarketSnapshot(
        hot_sectors=[item.model_dump() for item in load_live_hot_sectors(limit=8)],
        anomalies=load_live_anomalies(limit=10),
        longhubang=load_live_longhubang(limit=10),
        events=load_live_events(limit=10),
    )


def _score_watchlist_item(item: WatchlistItem, snapshot: PersistedMarketSnapshot) -> dict[str, Any]:
    symbol = item.symbol.upper()
    aliases = symbol_aliases(item.symbol)
    name = item.display_name.strip()
    sector = (item.sector or '').strip()
    tags = [tag.strip() for tag in item.tags if tag.strip()]

    score = 0.0
    reasons: list[str] = []
    matched_sources = 0

    for anomaly in snapshot.anomalies:
        text = f'{anomaly.title} {anomaly.summary} {anomaly.stock_code or ""} {anomaly.stock_name or ""}'
        if _match_symbol_text(aliases, text) or _match_text(name, text):
            score += 32
            reasons.append(f'市场异动命中：{anomaly.title}')
            matched_sources += 1
            break

    for item_lhb in snapshot.longhubang:
        text = f'{item_lhb.stock_code} {item_lhb.stock_name} {item_lhb.reason}'
        if _match_symbol_text(aliases, text) or _match_text(name, text):
            score += 28
            reasons.append(f'龙虎榜命中：{item_lhb.stock_name} {item_lhb.reason}')
            matched_sources += 1
            if str(item_lhb.net_amount).startswith('-'):
                score -= 6
                reasons.append('龙虎榜净额偏弱，做负向修正')
            else:
                score += 6
                reasons.append('龙虎榜净额非负，做正向修正')
            break

    for event in snapshot.events:
        text = f'{event.title} {event.summary}'
        if _match_text(symbol, text) or _match_text(name, text):
            score += 16
            reasons.append(f'事件流命中：{event.title}')
            matched_sources += 1
            if event.sentiment == 'positive':
                score += 8
            elif event.sentiment == 'negative':
                score -= 8
            break

    if sector:
        for hot_sector in snapshot.hot_sectors:
            text = f'{hot_sector.get("name", "")} {hot_sector.get("thesis", "")}'
            if _match_text(sector, text):
                score += 18
                reasons.append(f'板块热度命中：{hot_sector.get("name", "")}')
                matched_sources += 1
                break

    tag_hits = 0
    for tag in tags:
        matched = False
        for hot_sector in snapshot.hot_sectors:
            text = f'{hot_sector.get("name", "")} {hot_sector.get("thesis", "")}'
            if _match_text(tag, text):
                matched = True
                break
        if not matched:
            for event in snapshot.events:
                text = f'{event.title} {event.summary}'
                if _match_text(tag, text):
                    matched = True
                    break
        if matched:
            tag_hits += 1

    if tag_hits:
        bonus = min(20, tag_hits * 7)
        score += bonus
        reasons.append(f'标签命中 {tag_hits} 项，增加 {bonus:.0f} 分')
        matched_sources += 1

    score = max(0.0, min(100.0, score))
    confidence = max(0.2, min(0.95, 0.2 + matched_sources * 0.18 + score / 180))

    if score >= 70:
        action = 'strong_watch'
    elif score >= 45:
        action = 'watch'
    elif score >= 20:
        action = 'observe'
    else:
        action = 'ignore'

    if not reasons:
        reasons.append('当前实时事件/异动/板块中尚未发现直接命中')

    summary = reasons[0]
    return {
        'watchlist_id': item.id,
        'symbol': symbol,
        'display_name': item.display_name,
        'score': round(score, 2),
        'confidence': round(confidence, 2),
        'action': action,
        'summary': summary,
        'reasons': reasons[:6],
    }


def sync_signals() -> SignalSyncResponse:
    store = get_local_store()
    watchlist = store.list_watchlist()
    snapshot = _build_snapshot()
    snapshot_id = store.record_snapshot(snapshot.model_dump())

    if not watchlist:
        return SignalSyncResponse(
            snapshot_id=snapshot_id,
            watchlist_count=0,
            signal_count=0,
            notes=['watchlist 为空，已保存市场快照但未生成信号。'],
            top_signals=[],
        )

    raw_signals = [_score_watchlist_item(item, snapshot) for item in watchlist]
    saved = store.replace_signals(snapshot_id=snapshot_id, signals=raw_signals)
    top_signals = [signal for signal in saved if signal.action != 'ignore'][:10]
    if not top_signals:
        top_signals = saved[:10]

    notes = [
        f'已保存 {len(snapshot.events)} 条事件、{len(snapshot.anomalies)} 条异动、{len(snapshot.longhubang)} 条龙虎榜记录。',
        '当前 signal 为规则评分版，后续可替换为事件因子 / 图谱传播 / LLM 解释增强。',
    ]

    return SignalSyncResponse(
        snapshot_id=snapshot_id,
        watchlist_count=len(watchlist),
        signal_count=len(saved),
        notes=notes,
        top_signals=top_signals,
    )


def list_latest_signals(limit: int = 20) -> list[SignalItem]:
    return get_local_store().list_signals(limit=limit)
