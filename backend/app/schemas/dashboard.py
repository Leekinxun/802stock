from pydantic import BaseModel

from app.schemas.common import MetricCard
from app.schemas.event import EventFeedItem


class HotSectorItem(BaseModel):
    name: str
    change_pct: str
    leader: str
    thesis: str
    code: str | None = None
    source: str | None = None


class StrategyWorkbenchItem(BaseModel):
    name: str
    status: str
    note: str


class MigrationStatus(BaseModel):
    completed: list[str]
    next_up: list[str]
    blockers: list[str]


class PlatformStatus(BaseModel):
    legacy_root: str
    module_counts: dict[str, int]
    todo_count: int
    implemented_collectors: list[str]
    critical_findings: list[str]


class DashboardPayload(BaseModel):
    metrics: list[MetricCard]
    hot_sectors: list[HotSectorItem]
    event_stream: list[EventFeedItem]
    strategy_workbench: list[StrategyWorkbenchItem]
    migration: MigrationStatus
    platform_status: PlatformStatus
