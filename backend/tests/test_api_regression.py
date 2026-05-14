from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / 'backend'
TEST_DB_PATH = PROJECT_ROOT / 'backend' / '.runtime' / 'test_api_regression.db'

os.environ['QUANT_SQLITE_PATH'] = str(TEST_DB_PATH)
sys.path.insert(0, str(BACKEND_ROOT))

from app.main import app  # noqa: E402
from app.schemas.dashboard import HotSectorItem, MigrationStatus, PlatformStatus  # noqa: E402
from app.schemas.event import EventFeedItem  # noqa: E402
from app.schemas.market import (  # noqa: E402
    IntradayTrendPoint,
    IntradayTrendResponse,
    LonghubangItem,
    MarketAnomalyItem,
    MarketSentimentPoint,
    MarketSentimentResponse,
    WencaiIntersectionJobCreateResponse,
    WencaiIntersectionJobResponse,
    RealtimeOrderFlow,
    RealtimeQuoteResponse,
    WencaiIntersectionResponse,
    WencaiIntersectionStepResult,
    WencaiQueryResponse,
)
from app.services import local_store  # noqa: E402


class ApiRegressionTest(unittest.TestCase):
    def setUp(self) -> None:
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()
        local_store._STORE = None
        self.client = TestClient(app)

    def tearDown(self) -> None:
        local_store._STORE = None
        if TEST_DB_PATH.exists():
            TEST_DB_PATH.unlink()

    def test_health_endpoint(self) -> None:
        response = self.client.get('/api/v1/health')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['status'], 'ok')

    @patch('app.services.signal_engine.load_live_events')
    @patch('app.services.signal_engine.load_live_longhubang')
    @patch('app.services.signal_engine.load_live_anomalies')
    @patch('app.services.signal_engine.load_live_hot_sectors')
    def test_watchlist_and_signal_sync_flow(
        self,
        mock_hot_sectors,
        mock_anomalies,
        mock_longhubang,
        mock_events,
    ) -> None:
        mock_hot_sectors.return_value = [
            HotSectorItem(
                name='半导体',
                change_pct='+3.8%',
                leader='中芯国际',
                thesis='产业链集体走强',
                code='BK001',
                source='test',
            )
        ]
        mock_anomalies.return_value = [
            MarketAnomalyItem(
                title='中芯国际 涨停雷达',
                stock_code='SH688981',
                stock_name='中芯国际',
                anomaly_type='涨停雷达',
                summary='先进制程逻辑强化',
                timestamp='2026-04-27 22:00',
                source='test',
            )
        ]
        mock_longhubang.return_value = [
            LonghubangItem(
                stock_code='SH688981',
                stock_name='中芯国际',
                reason='机构净买入',
                net_amount='1234万',
                buy_total='4567万',
                sell_total='1200万',
                timestamp='2026-04-27',
                source='test',
            )
        ]
        mock_events.return_value = [
            EventFeedItem(
                title='中芯国际 获订单超预期',
                source='test',
                timestamp='2026-04-27 22:00',
                sentiment='positive',
                summary='半导体景气度提升',
            )
        ]

        create_response = self.client.post(
            '/api/v1/watchlist',
            json={
                'symbol': '688981.SH',
                'display_name': '中芯国际',
                'sector': '半导体',
                'tags': ['半导体', '先进制程'],
                'note': '核心观察标的',
            },
        )
        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.json()['symbol'], '688981.SH')

        sync_response = self.client.post('/api/v1/signals/sync')
        self.assertEqual(sync_response.status_code, 200)
        sync_payload = sync_response.json()
        self.assertEqual(sync_payload['watchlist_count'], 1)
        self.assertEqual(sync_payload['signal_count'], 1)
        self.assertEqual(len(sync_payload['top_signals']), 1)
        self.assertIn(sync_payload['top_signals'][0]['action'], {'strong_watch', 'watch'})

        list_response = self.client.get('/api/v1/signals?limit=5')
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()['items']), 1)

    @patch('app.services.platform_summary.scan_legacy_repo_status')
    @patch('app.services.platform_summary.load_live_hot_sectors')
    @patch('app.services.platform_summary.load_live_events')
    def test_dashboard_aggregation_shape(
        self,
        mock_events,
        mock_hot_sectors,
        mock_repo_status,
    ) -> None:
        mock_repo_status.return_value = PlatformStatus(
            legacy_root='/tmp/stock',
            module_counts={'backend': 1},
            todo_count=0,
            implemented_collectors=['backend/app/legacy/collectors/event_collectors/announcement_collector.py'],
            critical_findings=['ok'],
        )
        mock_hot_sectors.return_value = [
            HotSectorItem(
                name='半导体',
                change_pct='+2.1%',
                leader='中芯国际',
                thesis='景气度回升',
                code='BK001',
                source='test',
            )
        ]
        mock_events.return_value = [
            EventFeedItem(
                title='测试事件',
                source='test',
                timestamp='2026-04-27 22:00',
                sentiment='neutral',
                summary='事件摘要',
            )
        ]

        response = self.client.get('/api/v1/dashboard?event_limit=3&sector_limit=3')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload['hot_sectors']), 1)
        self.assertEqual(len(payload['event_stream']), 1)
        self.assertIn('migration', payload)

    @patch('app.api.routes.market.load_live_intraday_trend')
    def test_intraday_trend_endpoint(self, mock_intraday) -> None:
        mock_intraday.return_value = IntradayTrendResponse(
            symbol='600519',
            source='stockapi',
            supported=True,
            points=[
                IntradayTrendPoint(time='09:30', open=100.0, high=101.0, low=99.8, close=100.6, volume=1200.0, amount=350000.0),
                IntradayTrendPoint(time='09:31', open=100.6, high=101.5, low=100.4, close=101.2, volume=1800.0, amount=520000.0),
            ],
            open_price=100.0,
            latest_price=101.2,
            day_high=101.5,
            day_low=99.8,
            change_pct=1.2,
            note=None,
        )

        response = self.client.get('/api/v1/market/intraday/600519')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['supported'])
        self.assertEqual(payload['symbol'], '600519')
        self.assertEqual(len(payload['points']), 2)
        self.assertAlmostEqual(payload['latest_price'], 101.2)

    @patch('app.api.routes.market.load_live_realtime_quote')
    def test_realtime_quote_endpoint(self, mock_realtime) -> None:
        mock_realtime.return_value = RealtimeQuoteResponse(
            symbol='600519',
            market_symbol='sh600519',
            source='tencent-qt',
            supported=True,
            name='贵州茅台',
            price=1688.0,
            prev_close=1665.0,
            open_price=1670.0,
            high_price=1692.0,
            low_price=1668.0,
            change=23.0,
            change_pct=1.38,
            volume_hands=15230.0,
            amount_wan=258000.0,
            quote_time='2026-04-28 10:31:05',
            bid_price_1=1687.5,
            bid_volume_1=120.0,
            ask_price_1=1688.0,
            ask_volume_1=86.0,
            order_flow=RealtimeOrderFlow(
                buy_large=0.32,
                buy_small=0.18,
                sell_large=0.14,
                sell_small=0.21,
            ),
            note=None,
        )

        response = self.client.get('/api/v1/market/realtime/600519')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['supported'])
        self.assertEqual(payload['source'], 'tencent-qt')
        self.assertEqual(payload['market_symbol'], 'sh600519')
        self.assertAlmostEqual(payload['price'], 1688.0)
        self.assertEqual(payload['order_flow']['buy_large'], 0.32)

    @patch('app.api.routes.market.load_market_sentiment')
    def test_market_sentiment_endpoint(self, mock_sentiment) -> None:
        mock_sentiment.return_value = MarketSentimentResponse(
            points=[
                MarketSentimentPoint(
                    trade_date='2026-04-24',
                    rise_count=3120,
                    total_count=5380,
                    ratio=3120 / 5380,
                    source='eastmoney',
                    note=None,
                ),
                MarketSentimentPoint(
                    trade_date='2026-04-25',
                    rise_count=2840,
                    total_count=5380,
                    ratio=2840 / 5380,
                    source='eastmoney',
                    note=None,
                ),
            ],
            supported=True,
            source='eastmoney',
            latest_trade_date='2026-04-25',
            note='最近 2 个交易日记录已返回。',
        )

        response = self.client.get('/api/v1/market/sentiment?limit=5')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['supported'])
        self.assertEqual(payload['source'], 'eastmoney')
        self.assertEqual(payload['latest_trade_date'], '2026-04-25')
        self.assertEqual(len(payload['points']), 2)
        self.assertEqual(payload['points'][0]['trade_date'], '2026-04-24')

    @patch('app.api.routes.market.load_delisted_stocks')
    def test_delisted_stocks_endpoint(self, mock_delisted) -> None:
        mock_delisted.return_value = WencaiQueryResponse(
            query='退市股票',
            sort_key='退市@退市日期',
            sort_order='asc',
            query_type='stock',
            source='pywencai',
            supported=True,
            columns=['股票代码', '股票简称', '退市日期'],
            items=[
                {'股票代码': '600001.SH', '股票简称': '邯郸钢铁', '退市日期': '2024-01-01'},
            ],
            note=None,
        )

        response = self.client.get('/api/v1/market/delisted-stocks?limit=20')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['supported'])
        self.assertEqual(payload['source'], 'pywencai')
        self.assertEqual(payload['query'], '退市股票')

    @patch('app.api.routes.market.run_wencai_intersection')
    def test_wencai_intersection_endpoint(self, mock_intersection) -> None:
        mock_intersection.return_value = WencaiIntersectionResponse(
            query='条件一 ∩ 条件二',
            sort_key='涨停次数',
            sort_order='desc',
            query_type='stock',
            source='pywencai-intersection',
            supported=True,
            columns=['股票代码', '股票简称'],
            items=[{'股票代码': '000001.SZ', '股票简称': '平安银行'}],
            requested_query_count=2,
            executed_query_count=2,
            intersection_count=1,
            watchlist_added_count=1,
            watchlist_existing_count=0,
            step_results=[
                WencaiIntersectionStepResult(query='条件一', supported=True, item_count=3, note=None),
                WencaiIntersectionStepResult(query='条件二', supported=True, item_count=2, note=None),
            ],
            note='已完成 2 次问财查询，交集 1 只；观察池新增 1 只，已存在 0 只。',
        )

        response = self.client.post(
            '/api/v1/market/wencai-intersection',
            json={
                'queries': ['条件一', '条件二'],
                'sort_key': '涨停次数',
                'sort_order': 'desc',
                'limit': 20,
                'query_type': 'stock',
                'interval_seconds': 90,
                'import_to_watchlist': True,
            },
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['supported'])
        self.assertEqual(payload['intersection_count'], 1)
        self.assertEqual(payload['watchlist_added_count'], 1)
        self.assertEqual(len(payload['step_results']), 2)
        self.assertEqual(payload['items'][0]['股票代码'], '000001.SZ')

    @patch('app.api.routes.market.create_wencai_intersection_job')
    def test_wencai_intersection_job_create_endpoint(self, mock_create_job) -> None:
        mock_create_job.return_value = WencaiIntersectionJobCreateResponse(
            job_id='job-123',
            status='pending',
            created_at='2026-04-28T10:00:00',
            requested_query_count=3,
            poll_after_seconds=5,
            note='任务已创建，等待后台执行。',
        )

        response = self.client.post(
            '/api/v1/market/wencai-intersection/jobs',
            json={
                'queries': ['条件一', '条件二', '条件三'],
                'sort_key': '涨停次数',
                'sort_order': 'desc',
                'limit': 20,
                'query_type': 'stock',
                'interval_seconds': 90,
                'import_to_watchlist': True,
            },
        )

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload['job_id'], 'job-123')
        self.assertEqual(payload['requested_query_count'], 3)

    @patch('app.api.routes.market.get_wencai_intersection_job')
    def test_wencai_intersection_job_detail_endpoint(self, mock_get_job) -> None:
        mock_get_job.return_value = WencaiIntersectionJobResponse(
            job_id='job-123',
            status='running',
            created_at='2026-04-28T10:00:00',
            updated_at='2026-04-28T10:01:00',
            started_at='2026-04-28T10:00:10',
            completed_at=None,
            requested_query_count=3,
            executed_query_count=1,
            step_results=[
                WencaiIntersectionStepResult(query='条件一', supported=True, item_count=12, note=None),
            ],
            note='第 1 / 3 条执行完成，返回 12 条结果。',
            result=None,
        )

        response = self.client.get('/api/v1/market/wencai-intersection/jobs/job-123')
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload['status'], 'running')
        self.assertEqual(payload['executed_query_count'], 1)
        self.assertEqual(len(payload['step_results']), 1)

    @patch('app.api.routes.market.run_wencai_query')
    def test_generic_wencai_query_endpoint(self, mock_query) -> None:
        mock_query.return_value = WencaiQueryResponse(
            query='沪深主板且非ST且价格小于23',
            sort_key='涨停次数',
            sort_order='desc',
            query_type='stock',
            source='pywencai',
            supported=True,
            columns=['股票代码', '股票简称'],
            items=[{'股票代码': '002594.SZ', '股票简称': '比亚迪'}],
            note=None,
        )

        response = self.client.post(
            '/api/v1/market/wencai-query',
            json={
                'query': '沪深主板且非ST且价格小于23且近10年涨停总数大于16',
                'sort_key': '涨停次数',
                'sort_order': 'desc',
                'limit': 20,
                'query_type': 'stock',
            },
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload['supported'])
        self.assertEqual(payload['source'], 'pywencai')
        self.assertEqual(payload['query_type'], 'stock')
        self.assertEqual(payload['items'][0]['股票代码'], '002594.SZ')


if __name__ == '__main__':
    unittest.main()
