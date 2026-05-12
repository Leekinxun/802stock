"""数据源基类"""
from abc import ABC, abstractmethod
from typing import List, Dict, Optional


class BaseDataSource(ABC):
    """数据源基类"""

    @abstractmethod
    def get_market_anomaly(self) -> List[Dict]:
        """获取市场异动数据"""
        pass

    @abstractmethod
    def get_longhubang(self, date: str) -> List[Dict]:
        """获取龙虎榜数据"""
        pass

    @abstractmethod
    def get_hot_sectors(self) -> List[Dict]:
        """获取热点板块数据"""
        pass

    @abstractmethod
    def get_capital_flow(self, stock_code: str, days: int = 1) -> List[Dict]:
        """获取资金流向数据"""
        pass
