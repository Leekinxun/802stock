from __future__ import annotations

import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import requests


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / 'backend'
sys.path.insert(0, str(BACKEND_ROOT))


class MarketSentimentTest(unittest.TestCase):
    def tearDown(self) -> None:
        for module_name in (
            'app.services.market_sentiment',
            'app.services.local_store',
            'app.core.config',
        ):
            sys.modules.pop(module_name, None)

    @staticmethod
    def _fetch_live_market_sentiment() -> tuple[int, int, float]:
        module = importlib.import_module('app.services.market_sentiment')
        return module._fetch_live_market_sentiment()

    def test_fetch_live_market_sentiment_paginates_full_market_not_first_page_only(self) -> None:
        def build_response(total: int, start: int, count: int, positive_count: int) -> Mock:
            diff = []
            for offset in range(count):
                index = start + offset
                diff.append({
                    'f12': f'{index:06d}',
                    'f14': f'Stock{index}',
                    'f3': 1.25 if offset < positive_count else -0.75,
                })

            response = Mock()
            response.raise_for_status.return_value = None
            response.json.return_value = {
                'data': {
                    'total': total,
                    'diff': diff,
                }
            }
            return response

        module = importlib.import_module('app.services.market_sentiment')
        with patch.object(module.requests, 'get') as mock_get:
            mock_get.side_effect = [
                build_response(total=180, start=1, count=100, positive_count=100),
                build_response(total=180, start=101, count=80, positive_count=0),
            ]

            rise_count, total_count, ratio = self._fetch_live_market_sentiment()

            self.assertEqual(rise_count, 100)
            self.assertEqual(total_count, 180)
            self.assertAlmostEqual(ratio, 100 / 180)
            self.assertEqual(mock_get.call_count, 2)

    def test_fetch_live_market_sentiment_retries_transient_gateway_errors(self) -> None:
        failure = requests.HTTPError('HTTP 502 for pn=2')

        def build_response(total: int, start: int, count: int, positive_count: int) -> Mock:
            diff = []
            for offset in range(count):
                index = start + offset
                diff.append({
                    'f12': f'{index:06d}',
                    'f14': f'Stock{index}',
                    'f3': 1.25 if offset < positive_count else -0.75,
                })

            response = Mock()
            response.status_code = 200
            response.raise_for_status.return_value = None
            response.json.return_value = {
                'data': {
                    'total': total,
                    'diff': diff,
                }
            }
            return response

        retry_response = Mock()
        retry_response.status_code = 502
        retry_response.raise_for_status.side_effect = failure

        module = importlib.import_module('app.services.market_sentiment')
        with patch.object(module, 'time') as mock_time, patch.object(module.requests, 'get') as mock_get:
            mock_get.side_effect = [
                build_response(total=120, start=1, count=100, positive_count=60),
                retry_response,
                build_response(total=120, start=101, count=20, positive_count=5),
            ]

            rise_count, total_count, ratio = self._fetch_live_market_sentiment()

            self.assertEqual(rise_count, 65)
            self.assertEqual(total_count, 120)
            self.assertAlmostEqual(ratio, 65 / 120)
            self.assertEqual(mock_get.call_count, 3)
            self.assertTrue(mock_time.sleep.called)


if __name__ == '__main__':
    unittest.main()
