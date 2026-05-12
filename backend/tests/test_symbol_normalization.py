from __future__ import annotations

import os
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / 'backend'
TEST_DB_PATH = PROJECT_ROOT / 'backend' / '.runtime' / 'test_symbol_normalization.db'
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import BACKEND_ROOT, PROJECT_ROOT, _resolve_project_path  # noqa: E402
from app.core.symbols import symbol_aliases, to_stockapi_code, to_tencent_code, to_ts_code  # noqa: E402
from app.legacy.datasources.stockapi_source import StockAPISource  # noqa: E402
from app.legacy.utils.http_client import HTTPClient  # noqa: E402
from app.services import live_legacy  # noqa: E402
from app.schemas.market import WencaiQueryResponse  # noqa: E402
from app.services import local_store  # noqa: E402
from app.services.wencai import load_delisted_stocks, run_wencai_intersection, run_wencai_query  # noqa: E402


class SymbolNormalizationTest(unittest.TestCase):
    def setUp(self) -> None:
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()
        local_store.settings.sqlite_path = str(TEST_DB_PATH)
        local_store._STORE = None

    def tearDown(self) -> None:
        local_store._STORE = None
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()

    def test_convert_csv_style_code_for_multiple_datasources(self) -> None:
        self.assertEqual(to_ts_code('000001.SH'), '000001.SH')
        self.assertEqual(to_stockapi_code('000001.SH'), 'SH000001')
        self.assertEqual(to_tencent_code('000001.SH'), 'sh000001')

        self.assertEqual(to_ts_code('SZ000001'), '000001.SZ')
        self.assertEqual(to_stockapi_code('000001.SZ'), 'SZ000001')
        self.assertEqual(to_tencent_code('SZ000001'), 'sz000001')

    def test_symbol_aliases_cover_cross_format_matching(self) -> None:
        aliases = symbol_aliases('688981.SH')
        self.assertIn('688981.SH', aliases)
        self.assertIn('SH688981', aliases)
        self.assertIn('sh688981', aliases)
        self.assertIn('688981', aliases)

    def test_relative_runtime_paths_are_resolved_from_project_root(self) -> None:
        resolved = _resolve_project_path('backend/.runtime/quant_platform.db', BACKEND_ROOT / '.runtime' / 'quant_platform.db')
        self.assertEqual(resolved, str(PROJECT_ROOT / 'backend' / '.runtime' / 'quant_platform.db'))

    @patch('app.legacy.utils.http_client.requests.Session.request')
    def test_http_client_accepts_none_headers(self, mock_request: Mock) -> None:
        response = Mock()
        response.raise_for_status.return_value = None
        mock_request.return_value = response

        client = HTTPClient(headers={'Authorization': 'Bearer test'})
        result = client.get('https://example.com/data')

        self.assertIs(result, response)
        _, kwargs = mock_request.call_args
        self.assertEqual(kwargs['headers']['Authorization'], 'Bearer test')
        self.assertEqual(kwargs['url'], 'https://example.com/data')

    @patch.dict(os.environ, {'STOCKAPI_KEY': 'test-key'}, clear=False)
    @patch('app.legacy.datasources.stockapi_source.HTTPClient.get')
    def test_stockapi_minute_kline_uses_market_prefixed_code(self, mock_get: Mock) -> None:
        response = Mock()
        response.json.return_value = {'data': []}
        mock_get.return_value = response

        source = StockAPISource()
        source.get_minute_kline('000001.SH', include_all=True)

        _, kwargs = mock_get.call_args
        self.assertEqual(kwargs['params']['code'], 'SH000001')
        self.assertEqual(kwargs['params']['all'], '1')

    def test_intraday_trend_is_explicitly_disabled(self) -> None:
        live_legacy._CACHE.clear()
        result = live_legacy.load_live_intraday_trend('002594.SZ')
        self.assertFalse(result.supported)
        self.assertEqual(result.source, 'disabled')
        self.assertEqual(result.points, [])
        self.assertIn('暂不提供', result.note or '')

    @patch('app.services.live_legacy.TencentQuoteSource.get_realtime_quote')
    def test_realtime_quote_does_not_fallback_to_stockapi_intraday(self, mock_get_realtime_quote: Mock) -> None:
        live_legacy._CACHE.clear()
        mock_get_realtime_quote.return_value = {
            'symbol': '002594.SZ',
            'market_symbol': 'sz002594',
            'source': 'tencent-qt',
            'supported': False,
            'note': '腾讯接口暂时不可用',
        }

        with patch('app.services.live_legacy.load_live_intraday_trend', side_effect=AssertionError('should not fallback')) as mock_intraday:
            result = live_legacy.load_live_realtime_quote('002594.SZ')

        self.assertFalse(result.supported)
        self.assertEqual(result.source, 'tencent-qt')
        self.assertIn('腾讯接口暂时不可用', result.note or '')
        mock_intraday.assert_not_called()

    @patch('app.services.live_legacy._load_tonghuashun_hot_sectors')
    def test_hot_sectors_now_come_from_tonghuashun_only(self, mock_hot_sectors: Mock) -> None:
        live_legacy._CACHE.clear()
        mock_hot_sectors.return_value = []
        live_legacy.load_live_hot_sectors(limit=3)
        mock_hot_sectors.assert_called_once_with(3)

    @patch.dict(os.environ, {}, clear=False)
    @patch('app.services.wencai.importlib.import_module', side_effect=ModuleNotFoundError('browser_cookie3'))
    def test_wencai_delisted_stocks_requires_cookie(self, _mock_import_module: Mock) -> None:
        original_cookie = os.environ.pop('WENCAI_COOKIE', None)
        try:
            result = load_delisted_stocks(limit=5)
        finally:
            if original_cookie is not None:
                os.environ['WENCAI_COOKIE'] = original_cookie

        self.assertFalse(result.supported)
        self.assertIn('Chrome Cookie', result.note or '')

    @patch.dict(os.environ, {'WENCAI_COOKIE': 'cookie=demo'}, clear=False)
    @patch('app.services.wencai.importlib.import_module')
    def test_wencai_delisted_stocks_serializes_rows(self, mock_import_module: Mock) -> None:
        class FakeFrame:
            columns = ['股票代码', '退市日期', '成交额']

            def to_dict(self, orient: str = 'records') -> list[dict[str, object]]:
                assert orient == 'records'
                return [
                    {'股票代码': '600001.SH', '退市日期': datetime(2024, 1, 1, 9, 30), '成交额': float('nan')},
                ]

        fake_module = Mock()
        fake_module.get.return_value = FakeFrame()
        mock_import_module.return_value = fake_module

        result = load_delisted_stocks(limit=5)
        self.assertTrue(result.supported)
        self.assertEqual(result.columns, ['股票代码', '退市日期', '成交额', '当日涨停价', '9.95%价格'])
        self.assertEqual(result.items[0]['股票代码'], '600001.SH')
        self.assertEqual(result.items[0]['退市日期'], '2024-01-01T09:30:00')
        self.assertIsNone(result.items[0]['成交额'])
        self.assertIsNone(result.items[0]['当日涨停价'])
        self.assertIsNone(result.items[0]['9.95%价格'])

    @patch.dict(os.environ, {}, clear=False)
    @patch('app.services.wencai.importlib.import_module')
    def test_wencai_can_auto_load_cookie_from_chrome(self, mock_import_module: Mock) -> None:
        original_cookie = os.environ.pop('WENCAI_COOKIE', None)

        class FakeCookie:
            def __init__(self, domain: str, name: str, value: str):
                self.domain = domain
                self.name = name
                self.value = value

        class FakeFrame:
            columns = ['股票代码']

            def to_dict(self, orient: str = 'records') -> list[dict[str, object]]:
                return [{'股票代码': '000001.SZ'}]

        browser_cookie3 = Mock()
        browser_cookie3.chrome.return_value = [
            FakeCookie('.iwencai.com', 'Hexin-V', 'abc'),
            FakeCookie('.10jqka.com.cn', 'THSSESSID', 'xyz'),
            FakeCookie('.example.com', 'ignored', 'nope'),
        ]

        pywencai_module = Mock()
        pywencai_module.get.return_value = FakeFrame()

        def fake_import(name: str) -> Mock:
            if name == 'browser_cookie3':
                return browser_cookie3
            if name == 'pywencai':
                return pywencai_module
            raise ModuleNotFoundError(name)

        mock_import_module.side_effect = fake_import

        try:
            result = load_delisted_stocks(limit=3)
        finally:
            if original_cookie is not None:
                os.environ['WENCAI_COOKIE'] = original_cookie

        self.assertTrue(result.supported)
        self.assertIn('Chrome', result.note or '')
        pywencai_module.get.assert_called_once()
        self.assertIn('Hexin-V=abc', pywencai_module.get.call_args.kwargs['cookie'])
        self.assertIn('THSSESSID=xyz', pywencai_module.get.call_args.kwargs['cookie'])

    @patch.dict(os.environ, {'WENCAI_COOKIE': 'cookie=demo'}, clear=False)
    @patch('app.services.wencai.importlib.import_module')
    def test_generic_wencai_query_passes_query_arguments(self, mock_import_module: Mock) -> None:
        class FakeFrame:
            columns = ['股票代码']

            def to_dict(self, orient: str = 'records') -> list[dict[str, object]]:
                return [{'股票代码': '000001.SZ'}]

        fake_module = Mock()
        fake_module.get.return_value = FakeFrame()
        mock_import_module.return_value = fake_module

        result = run_wencai_query(
            query='沪深主板且非ST且价格小于23',
            sort_key='涨停次数',
            sort_order='desc',
            limit=12,
            query_type='stock',
        )

        self.assertTrue(result.supported)
        fake_module.get.assert_called_once_with(
            query='沪深主板且非ST且价格小于23',
            sort_key='涨停次数',
            sort_order='desc',
            cookie='cookie=demo',
            perpage=12,
            query_type='stock',
            loop=False,
        )

    @patch.dict(os.environ, {'WENCAI_COOKIE': 'cookie=demo'}, clear=False)
    @patch('app.services.wencai.importlib.import_module')
    def test_wencai_query_adds_limit_up_price_for_different_boards(self, mock_import_module: Mock) -> None:
        class FakeFrame:
            columns = ['股票代码', '股票简称', '前收盘价']

            def to_dict(self, orient: str = 'records') -> list[dict[str, object]]:
                assert orient == 'records'
                return [
                    {'股票代码': '000001.SZ', '股票简称': '平安银行', '前收盘价': 10.00},
                    {'股票代码': '300750.SZ', '股票简称': '宁德时代', '前收盘价': 200.00},
                    {'股票代码': '688981.SH', '股票简称': '中芯国际', '前收盘价': 90.00},
                    {'股票代码': '430047.BJ', '股票简称': '诺思兰德', '前收盘价': 15.00},
                    {'股票代码': '600001.SH', '股票简称': 'ST秋林', '前收盘价': 2.34},
                ]

        fake_module = Mock()
        fake_module.get.return_value = FakeFrame()
        mock_import_module.return_value = fake_module

        result = run_wencai_query(query='测试条件', sort_key=None, sort_order=None, limit=10, query_type='stock')

        self.assertTrue(result.supported)
        self.assertIn('当日涨停价', result.columns)
        self.assertIn('9.95%价格', result.columns)
        self.assertEqual(result.items[0]['当日涨停价'], 11.0)
        self.assertEqual(result.items[1]['当日涨停价'], 240.0)
        self.assertEqual(result.items[2]['当日涨停价'], 108.0)
        self.assertEqual(result.items[3]['当日涨停价'], 19.5)
        self.assertEqual(result.items[4]['当日涨停价'], 2.46)
        self.assertEqual(result.items[0]['9.95%价格'], 10.99)
        self.assertEqual(result.items[1]['9.95%价格'], 219.9)
        self.assertEqual(result.items[2]['9.95%价格'], 98.95)
        self.assertEqual(result.items[3]['9.95%价格'], 16.49)
        self.assertEqual(result.items[4]['9.95%价格'], 2.57)

    @patch.dict(os.environ, {'WENCAI_COOKIE': 'cookie=demo'}, clear=False)
    @patch('app.services.wencai.importlib.import_module')
    def test_wencai_query_prefers_existing_limit_up_price(self, mock_import_module: Mock) -> None:
        class FakeFrame:
            columns = ['股票代码', '股票简称', '涨停价', '最新价']

            def to_dict(self, orient: str = 'records') -> list[dict[str, object]]:
                assert orient == 'records'
                return [
                    {'股票代码': '000001.SZ', '股票简称': '平安银行', '涨停价': 11.11, '最新价': 10.21},
                ]

        fake_module = Mock()
        fake_module.get.return_value = FakeFrame()
        mock_import_module.return_value = fake_module

        result = run_wencai_query(query='测试条件', sort_key=None, sort_order=None, limit=10, query_type='stock')

        self.assertTrue(result.supported)
        self.assertEqual(result.items[0]['当日涨停价'], 11.11)
        self.assertIsNone(result.items[0]['9.95%价格'])

    @patch.dict(os.environ, {'WENCAI_COOKIE': 'cookie=demo'}, clear=False)
    @patch('app.services.wencai.importlib.import_module')
    @patch('app.services.wencai.load_live_realtime_quote')
    def test_wencai_query_995_price_uses_prev_close_from_quote_when_missing_in_row(
        self,
        mock_load_realtime_quote: Mock,
        mock_import_module: Mock,
    ) -> None:
        class FakeFrame:
            columns = ['股票代码', '股票简称', '收盘价']

            def to_dict(self, orient: str = 'records') -> list[dict[str, object]]:
                assert orient == 'records'
                return [
                    {'股票代码': '000001.SZ', '股票简称': '平安银行', '收盘价': 10.21},
                ]

        fake_module = Mock()
        fake_module.get.return_value = FakeFrame()
        mock_import_module.return_value = fake_module
        mock_load_realtime_quote.return_value = Mock(prev_close=10.00)

        result = run_wencai_query(query='测试条件', sort_key=None, sort_order=None, limit=10, query_type='stock')

        self.assertTrue(result.supported)
        self.assertEqual(result.items[0]['当日涨停价'], 11.0)
        self.assertEqual(result.items[0]['9.95%价格'], 10.99)
        mock_load_realtime_quote.assert_called_once_with('000001.SZ')

    @patch.dict(os.environ, {'WENCAI_COOKIE': 'cookie=demo'}, clear=False)
    @patch('app.services.wencai.importlib.import_module')
    @patch('app.services.wencai.load_live_realtime_quote')
    def test_wencai_query_reuses_prev_close_lookup_per_symbol(
        self,
        mock_load_realtime_quote: Mock,
        mock_import_module: Mock,
    ) -> None:
        class FakeFrame:
            columns = ['股票代码', '股票简称']

            def to_dict(self, orient: str = 'records') -> list[dict[str, object]]:
                assert orient == 'records'
                return [
                    {'股票代码': '000001.SZ', '股票简称': '平安银行'},
                    {'股票代码': '000001.SZ', '股票简称': '平安银行'},
                ]

        fake_module = Mock()
        fake_module.get.return_value = FakeFrame()
        mock_import_module.return_value = fake_module
        mock_load_realtime_quote.return_value = Mock(prev_close=10.00)

        result = run_wencai_query(query='测试条件', sort_key=None, sort_order=None, limit=10, query_type='stock')

        self.assertTrue(result.supported)
        self.assertEqual(result.items[0]['9.95%价格'], 10.99)
        self.assertEqual(result.items[1]['9.95%价格'], 10.99)
        mock_load_realtime_quote.assert_called_once_with('000001.SZ')

    @patch.dict(os.environ, {'WENCAI_COOKIE': 'cookie=stale'}, clear=False)
    @patch('app.services.wencai.importlib.import_module')
    def test_wencai_retries_with_chrome_cookie_when_env_cookie_fails(self, mock_import_module: Mock) -> None:
        class FakeCookie:
            def __init__(self, domain: str, name: str, value: str):
                self.domain = domain
                self.name = name
                self.value = value

        class FakeFrame:
            columns = ['股票代码']

            def to_dict(self, orient: str = 'records') -> list[dict[str, object]]:
                return [{'股票代码': '002594.SZ'}]

        browser_cookie3 = Mock()
        browser_cookie3.chrome.return_value = [FakeCookie('.iwencai.com', 'Hexin-V', 'fresh')]

        pywencai_module = Mock()
        pywencai_module.get.side_effect = [
            RuntimeError('cookie expired'),
            FakeFrame(),
        ]

        def fake_import(name: str) -> Mock:
            if name == 'browser_cookie3':
                return browser_cookie3
            if name == 'pywencai':
                return pywencai_module
            raise ModuleNotFoundError(name)

        mock_import_module.side_effect = fake_import

        result = run_wencai_query(query='测试条件', sort_key=None, sort_order=None, limit=5, query_type='stock')
        self.assertTrue(result.supported)
        self.assertIn('回退到 Chrome', result.note or '')
        self.assertEqual(pywencai_module.get.call_count, 2)

    @patch('app.services.wencai.time.sleep')
    @patch('app.services.wencai.run_wencai_query')
    def test_wencai_intersection_runs_in_backend_and_imports_watchlist(
        self,
        mock_run_wencai_query: Mock,
        mock_sleep: Mock,
    ) -> None:
        mock_run_wencai_query.side_effect = [
            WencaiQueryResponse(
                query='条件一',
                sort_key='涨停次数',
                sort_order='desc',
                query_type='stock',
                source='pywencai',
                supported=True,
                columns=['股票代码', '股票简称'],
                items=[
                    {'股票代码': '000001.SZ', '股票简称': '平安银行'},
                    {'股票代码': '600519.SH', '股票简称': '贵州茅台'},
                ],
                note=None,
            ),
            WencaiQueryResponse(
                query='条件二',
                sort_key='涨停次数',
                sort_order='desc',
                query_type='stock',
                source='pywencai',
                supported=True,
                columns=['股票代码', '股票简称', '收盘价'],
                items=[
                    {'股票代码': '000001.SZ', '股票简称': '平安银行', '收盘价': 10.2},
                    {'股票代码': '300750.SZ', '股票简称': '宁德时代', '收盘价': 210.5},
                ],
                note=None,
            ),
        ]

        result = run_wencai_intersection(
            queries=['条件一', '条件二'],
            sort_key='涨停次数',
            sort_order='desc',
            limit=20,
            query_type='stock',
            interval_seconds=60,
            import_to_watchlist=True,
        )

        self.assertTrue(result.supported)
        self.assertEqual(result.intersection_count, 1)
        self.assertEqual(result.items[0]['股票代码'], '000001.SZ')
        self.assertEqual(result.watchlist_added_count, 1)
        self.assertEqual(result.watchlist_existing_count, 0)
        self.assertEqual(len(result.step_results), 2)
        mock_sleep.assert_called_once_with(60)

        store = local_store.get_local_store()
        watchlist = store.list_watchlist()
        self.assertEqual(len(watchlist), 1)
        self.assertEqual(watchlist[0].symbol, '000001.SZ')
        self.assertIn('问财交集', watchlist[0].tags)


if __name__ == '__main__':
    unittest.main()
