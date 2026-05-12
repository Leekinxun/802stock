"""
采集器基类
定义统一的数据采集接口
"""
from abc import ABC, abstractmethod
from typing import List, Optional

from app.legacy.storage.models import Event
from app.legacy.utils.http_client import HTTPClient
from app.legacy.utils.logger import get_logger


class BaseCollector(ABC):
    """采集器抽象基类"""

    def __init__(
        self,
        source_name: str,
        timeout: int = 30,
        max_retries: int = 3,
        retry_delay: int = 1
    ):
        """
        初始化采集器

        Args:
            source_name: 数据源名称
            timeout: 请求超时时间
            max_retries: 最大重试次数
            retry_delay: 重试延迟
        """
        self.source_name = source_name
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        # 初始化日志和HTTP客户端
        self.logger = get_logger(f"collectors.{self.__class__.__name__}")
        self.http_client = HTTPClient(
            timeout=timeout,
            max_retries=max_retries,
            retry_delay=retry_delay
        )

    @abstractmethod
    def collect(self, **kwargs) -> List[Event]:
        """
        采集数据

        Args:
            **kwargs: 采集参数

        Returns:
            事件列表

        Raises:
            Exception: 采集失败时抛出异常
        """
        pass

    def validate_event(self, event: Event) -> bool:
        """
        验证事件数据

        Args:
            event: 事件对象

        Returns:
            是否有效
        """
        try:
            # 基本字段验证
            if not event.title or not event.content:
                self.logger.warning(f"事件缺少必要字段: {event}")
                return False

            if not event.source:
                self.logger.warning(f"事件缺少数据源: {event}")
                return False

            return True

        except Exception as e:
            self.logger.error(f"事件验证失败: {e}")
            return False

    def filter_events(self, events: List[Event]) -> List[Event]:
        """
        过滤事件列表

        Args:
            events: 原始事件列表

        Returns:
            过滤后的事件列表
        """
        valid_events = []
        for event in events:
            if self.validate_event(event):
                valid_events.append(event)
            else:
                self.logger.debug(f"过滤无效事件: {event.title if hasattr(event, 'title') else 'Unknown'}")

        self.logger.info(f"采集 {len(events)} 条数据, 有效 {len(valid_events)} 条")
        return valid_events

    def run(self, **kwargs) -> List[Event]:
        """
        执行采集任务(带异常处理)

        Args:
            **kwargs: 采集参数

        Returns:
            事件列表
        """
        try:
            self.logger.info(f"开始采集: {self.source_name}")
            events = self.collect(**kwargs)
            filtered_events = self.filter_events(events)
            self.logger.info(f"采集完成: {self.source_name}, 获取 {len(filtered_events)} 条有效数据")
            return filtered_events

        except Exception as e:
            self.logger.error(f"采集失败: {self.source_name} - {str(e)}", exc_info=True)
            return []

    def close(self):
        """关闭资源"""
        if hasattr(self, 'http_client'):
            self.http_client.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
