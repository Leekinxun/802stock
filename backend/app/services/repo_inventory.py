from pathlib import Path

from app.schemas.dashboard import PlatformStatus

REPO_ROOT = Path(__file__).resolve().parents[3]
LEGACY_DIRS = [
    'backend',
    'frontend',
]

IMPLEMENTED_COLLECTORS = [
    'backend/app/legacy/collectors/event_collectors/announcement_collector.py',
    'backend/app/legacy/collectors/event_collectors/company_news_collector.py',
    'backend/app/legacy/collectors/event_collectors/zt_radar_collector.py',
    'backend/app/legacy/collectors/audience_collectors/stock_collector.py',
]

CRITICAL_FINDINGS = [
    '仓库已收敛为标准单项目结构：backend + frontend。',
    'legacy adapters 已收进 backend/app/legacy，后端代码边界更清晰。',
    '实时事件、异动、龙虎榜、热点板块、观察池、signal 同步均已打通。',
    '持久化当前使用本地 SQLite，便于继续演进到 PostgreSQL。',
    '当前实时行情依赖腾讯，市场级数据依赖同花顺源站，外部接口波动会影响实时数据。',
]


def _count_python_files(path: Path) -> int:
    return sum(1 for file in path.rglob('*.py') if file.is_file())


def _count_todos(path: Path) -> int:
    count = 0
    for file in path.rglob('*.py'):
        try:
            count += file.read_text(encoding='utf-8').count('TODO')
        except UnicodeDecodeError:
            continue
    return count


def scan_legacy_repo_status() -> PlatformStatus:
    module_counts = {}
    todo_count = 0

    for name in LEGACY_DIRS:
        target = REPO_ROOT / name
        if not target.exists():
            continue
        module_counts[name] = _count_python_files(target)
        todo_count += _count_todos(target)

    return PlatformStatus(
        legacy_root=str(REPO_ROOT),
        module_counts=module_counts,
        todo_count=todo_count,
        implemented_collectors=IMPLEMENTED_COLLECTORS,
        critical_findings=CRITICAL_FINDINGS,
    )
