"""腾讯实时行情数据源。"""
from __future__ import annotations

import random
from datetime import datetime
from typing import Any

from app.core.symbols import to_tencent_code
from app.legacy.utils.http_client import HTTPClient
from app.legacy.utils.logger import get_logger

logger = get_logger(__name__)


class TencentQuoteSource:
    """基于 qt.gtimg.cn 的实时快照与盘口数据源。"""

    BASE_URL = 'https://qt.gtimg.cn/q={symbols}'
    HEADERS_POOL = [
        {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Referer': 'https://finance.sina.com.cn/',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
            'Connection': 'keep-alive',
        },
        {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0',
            'Referer': 'https://finance.qq.com/',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.9',
            'Connection': 'keep-alive',
        },
        {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Referer': 'https://quote.eastmoney.com/',
            'Accept': '*/*',
            'Accept-Language': 'zh-CN,zh;q=0.8,en;q=0.6',
            'Connection': 'keep-alive',
        },
    ]

    NORMAL_INDEXES = {
        1: 'name',
        2: 'symbol_code',
        3: 'price',
        4: 'prev_close',
        5: 'open_price',
        9: 'bid_price_1',
        10: 'bid_volume_1',
        19: 'ask_price_1',
        20: 'ask_volume_1',
        30: 'quote_time',
        31: 'change',
        32: 'change_pct',
        33: 'high_price',
        34: 'low_price',
        36: 'volume_hands',
        37: 'amount_wan',
    }
    PK_INDEXES = {
        1: 'buy_large',
        2: 'buy_small',
        3: 'sell_large',
        4: 'sell_small',
    }

    def __init__(self) -> None:
        self.client = HTTPClient(timeout=3, max_retries=2, retry_delay=1)

    def _random_headers(self) -> dict[str, str]:
        headers = random.choice(self.HEADERS_POOL).copy()
        headers['Accept-Language'] = random.choice([
            'zh-CN,zh;q=0.9',
            'zh-CN,zh;q=0.8,en;q=0.6',
            'en-US,en;q=0.9',
        ])
        return headers

    def normalize_symbol(self, symbol: str) -> str:
        return to_tencent_code(symbol)

    def _safe_float(self, value: Any) -> float | None:
        try:
            if value in (None, '', '--'):
                return None
            return float(str(value).replace(',', ''))
        except (TypeError, ValueError):
            return None

    def _format_quote_time(self, raw_value: str) -> str | None:
        value = (raw_value or '').strip()
        if len(value) == 14 and value.isdigit():
            try:
                return datetime.strptime(value, '%Y%m%d%H%M%S').strftime('%Y-%m-%d %H:%M:%S')
            except ValueError:
                return value
        return value or None

    def _parse_payload(self, text: str, column_map: dict[int, str], *, symbol_prefix: str = '') -> dict[str, dict[str, str]]:
        result: dict[str, dict[str, str]] = {}

        for line in text.split(';'):
            line = line.strip()
            if not line or '="' not in line:
                continue

            key, payload = line.split('="', 1)
            payload = payload.rstrip('"')
            parts = payload.split('~')
            symbol = key.split('v_', 1)[-1]
            if symbol_prefix and symbol.startswith(symbol_prefix):
                symbol = symbol[len(symbol_prefix):]

            row: dict[str, str] = {}
            for index, field_name in column_map.items():
                if index < len(parts):
                    row[field_name] = parts[index].strip()
            result[symbol] = row

        return result

    def get_realtime_quote(self, symbol: str) -> dict[str, Any]:
        market_symbol = self.normalize_symbol(symbol)
        if not market_symbol.startswith(('sh', 'sz', 'bj', 'hk')):
            return {
                'symbol': symbol,
                'market_symbol': market_symbol,
                'source': 'tencent-qt',
                'supported': False,
                'note': '股票代码格式无法识别，无法请求腾讯实时行情。',
            }

        try:
            quote_response = self.client.get(
                self.BASE_URL.format(symbols=market_symbol),
                headers=self._random_headers(),
            )
            quote_rows = self._parse_payload(quote_response.text, self.NORMAL_INDEXES)
            quote_row = quote_rows.get(market_symbol, {})

            if not quote_row.get('name') or not quote_row.get('price'):
                return {
                    'symbol': symbol,
                    'market_symbol': market_symbol,
                    'source': 'tencent-qt',
                    'supported': False,
                    'note': '腾讯实时行情未返回有效快照。',
                }

            pk_response = self.client.get(
                self.BASE_URL.format(symbols=f's_pk{market_symbol}'),
                headers=self._random_headers(),
            )
            pk_rows = self._parse_payload(pk_response.text, self.PK_INDEXES, symbol_prefix='s_pk')
            pk_row = pk_rows.get(market_symbol, {})

            return {
                'symbol': quote_row.get('symbol_code') or symbol,
                'market_symbol': market_symbol,
                'source': 'tencent-qt',
                'supported': True,
                'name': quote_row.get('name'),
                'price': self._safe_float(quote_row.get('price')),
                'prev_close': self._safe_float(quote_row.get('prev_close')),
                'open_price': self._safe_float(quote_row.get('open_price')),
                'high_price': self._safe_float(quote_row.get('high_price')),
                'low_price': self._safe_float(quote_row.get('low_price')),
                'change': self._safe_float(quote_row.get('change')),
                'change_pct': self._safe_float(quote_row.get('change_pct')),
                'volume_hands': self._safe_float(quote_row.get('volume_hands')),
                'amount_wan': self._safe_float(quote_row.get('amount_wan')),
                'quote_time': self._format_quote_time(quote_row.get('quote_time', '')),
                'bid_price_1': self._safe_float(quote_row.get('bid_price_1')),
                'bid_volume_1': self._safe_float(quote_row.get('bid_volume_1')),
                'ask_price_1': self._safe_float(quote_row.get('ask_price_1')),
                'ask_volume_1': self._safe_float(quote_row.get('ask_volume_1')),
                'buy_large': self._safe_float(pk_row.get('buy_large')),
                'buy_small': self._safe_float(pk_row.get('buy_small')),
                'sell_large': self._safe_float(pk_row.get('sell_large')),
                'sell_small': self._safe_float(pk_row.get('sell_small')),
                'note': None,
            }
        except Exception as exc:
            logger.error(f'获取腾讯实时行情失败 {market_symbol}: {exc}')
            return {
                'symbol': symbol,
                'market_symbol': market_symbol,
                'source': 'tencent-qt',
                'supported': False,
                'note': f'腾讯实时行情请求失败：{exc}',
            }
