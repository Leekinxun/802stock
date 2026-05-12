"""公司新闻采集器"""
from typing import List
from datetime import datetime

from app.legacy.collectors.base import BaseCollector
from app.legacy.datasources.tonghuashun_source import TonghuashunSource
from app.legacy.storage.models import Event, EventType


class CompanyNewsCollector(BaseCollector):
    """公司新闻采集器"""

    def __init__(self, **kwargs):
        super().__init__(source_name="company_news", **kwargs)
        self.data_source = TonghuashunSource()

    def collect(self, limit: int = 20, **kwargs) -> List[Event]:
        """采集公司新闻"""
        events = []
        items = self.data_source.get_company_news(limit)

        for item in items:
            try:
                event = Event(
                    title=item['title'],
                    content=item['title'],
                    event_type=EventType.NEWS,
                    source="tonghuashun_news",
                    source_url=item.get('url', ''),
                    publish_time=self._parse_time(item.get('time', '')),
                    metadata={'raw_data': item}
                )
                events.append(event)
            except Exception as e:
                self.logger.warning(f"构建事件失败: {e}")

        return events

    def _parse_time(self, time_str: str) -> datetime:
        """解析时间字符串"""
        if not time_str:
            return datetime.now()
        try:
            return datetime.strptime(time_str, "%Y-%m-%d %H:%M")
        except:
            return datetime.now()
