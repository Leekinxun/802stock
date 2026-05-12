"""Stock API 数据源"""
import os
from typing import Dict, List

from app.core.symbols import to_stockapi_code
from app.legacy.datasources.base import BaseDataSource
from app.legacy.utils.http_client import HTTPClient
from app.legacy.utils.logger import get_logger

logger = get_logger(__name__)


class StockAPISource(BaseDataSource):
    """Stock API 数据源"""

    def __init__(self):
        self.api_key = os.environ.get("STOCKAPI_KEY")
        self.base_url = os.environ.get("STOCKAPI_BASE_URL", "https://api.stockapi.com.cn")

        if not self.api_key:
            raise ValueError("STOCKAPI_KEY 未配置")

        self.client = HTTPClient(
            timeout=int(os.environ.get("STOCKAPI_TIMEOUT", 30)),
            headers={"Authorization": f"Bearer {self.api_key}"}
        )

    def _build_v1_url(self, path: str) -> str:
        """构建官方 v1 文档接口 URL。"""
        base_url = self.base_url.rstrip('/')

        if '/v1' in base_url:
            base_url = base_url.split('/v1', 1)[0]
        if 'api.stockapi.com.cn' in base_url:
            base_url = base_url.replace('api.stockapi.com.cn', 'www.stockapi.com.cn')

        return f"{base_url}/v1{path}"

    def get_market_anomaly(self) -> List[Dict]:
        """获取市场异动数据"""
        result = []
        try:
            # 涨停池
            resp = self.client.get(f"{self.base_url}/market/zt_pool")
            zt_data = resp.json().get("data", [])
            for item in zt_data:
                item["anomaly_type"] = "涨停"
            result.extend(zt_data)

            # 跌停池
            resp = self.client.get(f"{self.base_url}/market/dt_pool")
            dt_data = resp.json().get("data", [])
            for item in dt_data:
                item["anomaly_type"] = "跌停"
            result.extend(dt_data)

            # 异动数据
            resp = self.client.get(f"{self.base_url}/market/anomaly")
            result.extend(resp.json().get("data", []))

        except Exception as e:
            logger.error(f"获取市场异动数据失败: {e}")

        return result

    def get_longhubang(self, date: str) -> List[Dict]:
        """获取龙虎榜数据"""
        try:
            resp = self.client.get(f"{self.base_url}/longhubang/list", params={"date": date})
            return resp.json().get("data", [])
        except Exception as e:
            logger.error(f"获取龙虎榜数据失败: {e}")
            return []

    def get_hot_sectors(self) -> List[Dict]:
        """获取热点板块数据"""
        try:
            resp = self.client.get(f"{self.base_url}/sector/hot")
            return resp.json().get("data", [])
        except Exception as e:
            logger.error(f"获取热点板块数据失败: {e}")
            return []

    def get_capital_flow(self, stock_code: str, days: int = 1) -> List[Dict]:
        """获取资金流向数据"""
        normalized_code = to_stockapi_code(stock_code)
        try:
            resp = self.client.get(
                f"{self.base_url}/capital/flow",
                params={"code": normalized_code, "days": days}
            )
            return resp.json().get("data", [])
        except Exception as e:
            logger.error(f"获取资金流向数据失败: {e}")
            return []

    def get_sector_stocks(self, sector_code: str) -> List[Dict]:
        """获取板块成分股"""
        try:
            resp = self.client.get(f"{self.base_url}/sector/stocks", params={"code": sector_code})
            return resp.json().get("data", [])
        except Exception as e:
            logger.error(f"获取板块成分股失败: {e}")
            return []

    def get_minute_kline(self, stock_code: str, *, include_all: bool = True) -> List[Dict]:
        """获取个股当日一分钟 K 线。"""
        normalized_code = to_stockapi_code(stock_code)
        try:
            resp = self.client.get(
                self._build_v1_url("/base/minkLine"),
                params={"code": normalized_code, "all": "1" if include_all else "0"},
            )
            return resp.json().get("data", [])
        except Exception as e:
            logger.error(f"获取分钟 K 线失败: {e}")
            return []
