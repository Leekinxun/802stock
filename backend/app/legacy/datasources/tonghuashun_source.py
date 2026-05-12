"""同花顺数据源"""
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from app.legacy.datasources.base import BaseDataSource
from app.legacy.utils.logger import get_logger

logger = get_logger(__name__)


class TonghuashunSource(BaseDataSource):
    """同花顺数据源"""

    def __init__(self):
        self.BASE_URL = "https://data.10jqka.com.cn"

    # -------- 通用请求方法 --------
    def _get(self, path: str, base_url: Optional[str] = None) -> str:
        url = (base_url or self.BASE_URL) + path
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
            "Connection": "keep-alive",
            "Referer": base_url or self.BASE_URL,
        }
        try:
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            logger.error(f"请求失败 {url}: {e}")
            return ""

    # -------- 数据获取接口 --------
    def get_market_anomaly(self) -> List[Dict]:
        """获取市场异动数据（同花顺暂不支持）"""
        return []

    def get_longhubang(self, date: str = None) -> List[Dict]:
        """获取龙虎榜数据（含营业部明细）"""
        html = self._get("/market/longhu/")
        return self._parse_longhubang_full(html)

    def get_hot_sectors(self) -> List[Dict]:
        """获取热点板块数据"""
        html = self._get("/gn/", base_url="http://q.10jqka.com.cn")
        return self._parse_table(html, ['date', 'name', 'event', 'leader'], min_cols=4)

    def get_capital_flow(self, stock_code: str, days: int = 1) -> List[Dict]:
        """获取资金流向数据"""
        html = self._get("/funds/ggzjl/")
        return self._parse_capital_flow(html, stock_code)

    def get_announcements(self, limit: int = 20) -> List[Dict]:
        """获取公司公告"""
        html = self._get("/gegugg_list/", base_url="http://stock.10jqka.com.cn")
        return self._parse_items(html, limit)

    def get_company_news(self, limit: int = 20) -> List[Dict]:
        """获取公司新闻"""
        html = self._get("/companynews_list/", base_url="http://stock.10jqka.com.cn")
        return self._parse_items(html, limit)

    def get_zt_radar_list(self, limit: int = 20) -> List[Dict]:
        """获取涨停雷达列表"""
        html = self._get("/mrnxgg_list/", base_url="http://yuanchuang.10jqka.com.cn")
        return self._parse_items(html, limit)

    # -------- 通用解析方法 --------
    def _parse_table(self, html: str, keys: List[str], min_cols: int) -> List[Dict]:
        """解析标准 table 格式"""
        result = []
        try:
            soup = BeautifulSoup(html, 'html.parser')
            table = soup.find('table')
            if not table:
                return result
            tbody = table.find('tbody')
            if not tbody:
                return result
            for row in tbody.find_all('tr'):
                tds = row.find_all('td')
                if len(tds) >= min_cols:
                    result.append({k: tds[i].get_text(strip=True) for i, k in enumerate(keys)})
        except Exception as e:
            logger.error(f"解析表格失败: {e}")
        return result

    def _parse_items(self, html: str, limit: int) -> List[Dict]:
        """解析公告或新闻列表"""
        result = []
        try:
            soup = BeautifulSoup(html, 'html.parser')
            items = soup.find_all('a', class_='news-link', limit=limit)
            for a_tag in items:
                title = a_tag.get_text(strip=True)
                if title and len(title) > 5:  # 过滤太短的标题
                    result.append({
                        'title': title,
                        'url': a_tag.get('href', ''),
                        'time': '',  # 时间需要从其他地方提取
                    })
        except Exception as e:
            logger.error(f"解析列表失败: {e}")
        return result

    def _parse_longhubang_full(self, html: str) -> List[Dict]:
        """解析龙虎榜完整数据（含营业部明细）"""
        result = []
        try:
            soup = BeautifulSoup(html, 'html.parser')
            tables = soup.find_all('table', {'class': 'm-table'})
            if len(tables) < 2:
                return result

            # 第2个表格是股票列表
            stock_table = tables[1]
            stock_rows = stock_table.find_all('tr')

            # 解析每只股票及其营业部明细
            table_idx = 2  # 营业部明细从第3个表格开始
            for row in stock_rows:
                tds = row.find_all('td')
                if len(tds) >= 6:
                    stock_data = {
                        'date': tds[0].get_text(strip=True),
                        'code': tds[1].get_text(strip=True),
                        'name': tds[2].get_text(strip=True),
                        'price': tds[3].get_text(strip=True),
                        'change_pct': tds[4].get_text(strip=True),
                        'amount': tds[5].get_text(strip=True),
                        'net_buy': tds[6].get_text(strip=True) if len(tds) > 6 else '',
                        'buy_seats': [],
                        'sell_seats': [],
                    }

                    # 解析买入营业部（当前表格）
                    if table_idx < len(tables):
                        buy_table = tables[table_idx]
                        stock_data['buy_seats'] = self._parse_seats(buy_table)
                        table_idx += 1

                    # 解析卖出营业部（下一个表格）
                    if table_idx < len(tables):
                        sell_table = tables[table_idx]
                        stock_data['sell_seats'] = self._parse_seats(sell_table)
                        table_idx += 1

                    result.append(stock_data)

        except Exception as e:
            logger.error(f"解析龙虎榜失败: {e}")
        return result

    def _parse_seats(self, table) -> List[Dict]:
        """解析营业部席位数据"""
        seats = []
        try:
            rows = table.find_all('tr')
            for row in rows[1:]:  # 跳过表头
                tds = row.find_all('td')
                if len(tds) >= 4:
                    seat_name = tds[0].get_text(strip=True)
                    # 提取游资标签
                    tags = []
                    if '一线游资' in seat_name:
                        tags.append('一线游资')
                    if '知名游资' in seat_name:
                        tags.append('知名游资')
                    if '机构专用' in seat_name:
                        tags.append('机构')
                    if '深股通' in seat_name or '沪股通' in seat_name:
                        tags.append('北向资金')

                    seats.append({
                        'name': seat_name.replace('一线游资', '').replace('知名游资', '').replace('机构专用', '').strip(),
                        'buy_amount': tds[1].get_text(strip=True),
                        'sell_amount': tds[2].get_text(strip=True),
                        'net_amount': tds[3].get_text(strip=True),
                        'tags': tags,
                    })
        except Exception as e:
            logger.error(f"解析席位失败: {e}")
        return seats

    def _parse_capital_flow(self, html: str, stock_code: str) -> List[Dict]:
        """解析资金流向HTML（需要具体实现）"""
        # TODO: 根据实际页面结构解析资金流
        return []

