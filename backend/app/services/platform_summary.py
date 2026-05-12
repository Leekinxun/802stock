from datetime import datetime, timezone

from app.schemas.common import MetricCard
from app.schemas.dashboard import (
    DashboardPayload,
    HotSectorItem,
    MigrationStatus,
    StrategyWorkbenchItem,
)
from app.schemas.event import EventFeedItem, EventFeedResponse
from app.services.live_legacy import load_live_events, load_live_hot_sectors
from app.services.repo_inventory import scan_legacy_repo_status


def _now_label() -> str:
    return datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M')


def build_event_feed(limit: int = 9) -> EventFeedResponse:
    live_items = load_live_events(limit=limit)
    if live_items:
        return EventFeedResponse(items=live_items)

    timestamp = _now_label()
    return EventFeedResponse(
        items=[
            EventFeedItem(
                title='热点板块轮动观察',
                source='platform-demo',
                timestamp=timestamp,
                sentiment='positive',
                summary='当实时源暂不可用时，使用平台内置示例事件作为占位。',
            ),
            EventFeedItem(
                title='龙虎榜资金异动跟踪',
                source='platform-demo',
                timestamp=timestamp,
                sentiment='neutral',
                summary='建议继续强化腾讯 / 同花顺 adapter 的稳定性与缓存策略。',
            ),
            EventFeedItem(
                title='量化平台迁移开始',
                source='repo-audit',
                timestamp=timestamp,
                sentiment='positive',
                summary='当前仓库已整理为 backend + frontend 单项目结构，并保留最小 legacy adapters。',
            ),
        ]
    )


def build_dashboard_payload(event_limit: int = 9, sector_limit: int = 6) -> DashboardPayload:
    status = scan_legacy_repo_status()
    event_feed = build_event_feed(limit=event_limit).items
    hot_sectors = load_live_hot_sectors(limit=sector_limit)

    metrics = [
        MetricCard(label='Active Python Modules', value=str(sum(status.module_counts.values())), hint='收缩后仓库 Python 文件总量', tone='info'),
        MetricCard(label='Pending TODOs', value=str(status.todo_count), hint='当前保留代码中的待完善 TODO 数', tone='warning'),
        MetricCard(label='Live Collectors', value=str(len(status.implemented_collectors)), hint='仍在为新平台供数的 legacy 采集器', tone='success'),
        MetricCard(label='Frontend Status', value='React workbench ready', hint='前端已接 watchlist / signal / market panels', tone='accent'),
    ]

    if not hot_sectors:
        hot_sectors = [
            HotSectorItem(name='算力 / AI Infra', change_pct='+3.6%', leader='中际旭创', thesis='高景气延续，适合事件 + 趋势联动评分'),
            HotSectorItem(name='低空经济', change_pct='+2.8%', leader='万丰奥威', thesis='政策催化型板块，适合公告/新闻驱动跟踪'),
            HotSectorItem(name='机器人', change_pct='+2.1%', leader='鸣志电器', thesis='适合与产业链图谱、供应链关系联动观察'),
        ]

    strategy_workbench = [
        StrategyWorkbenchItem(name='事件驱动观察池', status='building', note='已支持 watchlist 持久化与信号同步。'),
        StrategyWorkbenchItem(name='热点板块轮动', status='building', note='已接入热点板块、异动、龙虎榜与事件流。'),
        StrategyWorkbenchItem(name='Signal 规则评分', status='building', note='当前为规则评分版，可继续升级为因子/图谱/LLM 解释。'),
        StrategyWorkbenchItem(name='组合与风险', status='planned', note='下一阶段可在现有 signal 基础上加入 portfolio / positions / exposure。'),
    ]

    migration = MigrationStatus(
        completed=[
            '完成 STOCK 旧代码现状审计',
            '完成 FastAPI 后端与 React 前端工作台搭建',
            '打通 legacy collectors -> FastAPI dashboard/events 接口',
            '打通 market snapshot / anomalies / longhubang',
            '引入 watchlist、SQLite 持久化与 signal 同步',
            '删除未接入的旧 Flask/分析/决策/图谱/调度脚手架',
            '将 legacy adapters 收拢到 backend/app/legacy 单项目结构',
        ],
        next_up=[
            '把 SQLite repository 升级为 PostgreSQL repository',
            '补充 signal explain / factor breakdown',
            '引入 portfolio / positions / risk exposure',
            '为实时抓取增加更稳健的缓存与容错策略',
        ],
        blockers=[
            '部分数据源需要 API Key 或网页结构稳定性验证',
            '当前 signal 仍是规则评分，不是成熟量化因子模型',
        ],
    )

    return DashboardPayload(
        metrics=metrics,
        hot_sectors=hot_sectors,
        event_stream=event_feed,
        strategy_workbench=strategy_workbench,
        migration=migration,
        platform_status=status,
    )
