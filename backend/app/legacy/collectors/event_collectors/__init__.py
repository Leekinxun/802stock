"""当前仍在使用的事件采集器。"""

from app.legacy.collectors.event_collectors.announcement_collector import AnnouncementCollector
from app.legacy.collectors.event_collectors.company_news_collector import CompanyNewsCollector
from app.legacy.collectors.event_collectors.zt_radar_collector import ZTRadarCollector

__all__ = ['AnnouncementCollector', 'CompanyNewsCollector', 'ZTRadarCollector']
