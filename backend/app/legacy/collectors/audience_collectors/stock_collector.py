"""
股票信息采集器
采集股票基础信息，集成 Stock API 板块概念数据
"""
from typing import List, Optional

from app.legacy.collectors.base import BaseCollector
from app.legacy.datasources import StockAPISource
from app.legacy.storage.models import Stock


class StockCollector(BaseCollector):
    """股票信息采集器"""

    def __init__(self, **kwargs):
        """初始化股票信息采集器"""
        super().__init__(source_name="stock_info", **kwargs)
        self.stockapi_source = StockAPISource()

    def collect(self, **kwargs) -> List[Stock]:
        """采集股票基础信息"""
        self.logger.info("采集股票基础信息...")
        return []

    def collect_stock_detail(self, stock_code: str) -> Optional[Stock]:
        """采集单个股票详细信息"""
        self.logger.info(f"采集股票详情: {stock_code}")
        return None

    def enrich_with_sector_data(self, sector_code: str) -> List[Stock]:
        """使用 Stock API 板块数据丰富股票信息"""
        try:
            stocks_data = self.stockapi_source.get_sector_stocks(sector_code)
            stocks = []
            for item in stocks_data:
                stock = Stock(
                    code=item.get('code'),
                    name=item.get('name'),
                    exchange=item.get('exchange', 'SH' if item.get('code', '').startswith('6') else 'SZ'),
                    sector=item.get('sector_name'),
                    metadata={
                        "data_source": "stockapi",
                        "sector_code": sector_code,
                        "concepts": item.get('concepts', [])
                    }
                )
                stocks.append(stock)
            self.logger.info(f"从 Stock API 获取板块 {sector_code} 成分股 {len(stocks)} 只")
            return stocks
        except Exception as e:
            self.logger.error(f"获取板块成分股失败: {e}")
            return []
