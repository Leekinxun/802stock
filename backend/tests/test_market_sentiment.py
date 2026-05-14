from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / 'backend'
os.environ.setdefault('QUANT_SQLITE_PATH', str(PROJECT_ROOT / 'backend' / '.runtime' / 'test_market_sentiment.db'))
sys.path.insert(0, str(BACKEND_ROOT))

from app.services.market_sentiment import _fetch_live_market_sentiment  # noqa: E402


class MarketSentimentTest(unittest.TestCase):
    @patch('app.services.market_sentiment.requests.get')
    def test_fetch_live_market_sentiment_paginates_full_market_not_first_page_only(self, mock_get: Mock) -> None:
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

        mock_get.side_effect = [
            build_response(total=180, start=1, count=100, positive_count=100),
            build_response(total=180, start=101, count=80, positive_count=0),
        ]

        rise_count, total_count, ratio = _fetch_live_market_sentiment()

        self.assertEqual(rise_count, 100)
        self.assertEqual(total_count, 180)
        self.assertAlmostEqual(ratio, 100 / 180)
        self.assertEqual(mock_get.call_count, 2)


if __name__ == '__main__':
    unittest.main()
