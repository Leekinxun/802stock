from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ROOT = PROJECT_ROOT / 'backend'
sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import _load_dotenv  # noqa: E402
from app.services.wencai_cookie_env import _upsert_env_value, sync_wencai_cookie_to_env  # noqa: E402


class WencaiCookieEnvSyncTest(unittest.TestCase):
    def test_load_dotenv_prefers_project_wencai_cookie_over_existing_env(self) -> None:
        original_cookie = os.environ.get('WENCAI_COOKIE')
        original_other = os.environ.get('SOME_OTHER_KEY')

        try:
            os.environ['WENCAI_COOKIE'] = 'stale-cookie'
            os.environ['SOME_OTHER_KEY'] = 'shell-value'

            with TemporaryDirectory() as tmpdir:
                dotenv_path = Path(tmpdir) / '.env'
                dotenv_path.write_text(
                    'WENCAI_COOKIE=fresh-cookie\nSOME_OTHER_KEY=dotenv-value\n',
                    encoding='utf-8',
                )

                _load_dotenv(dotenv_path)

            self.assertEqual(os.environ['WENCAI_COOKIE'], 'fresh-cookie')
            self.assertEqual(os.environ['SOME_OTHER_KEY'], 'shell-value')
        finally:
            if original_cookie is None:
                os.environ.pop('WENCAI_COOKIE', None)
            else:
                os.environ['WENCAI_COOKIE'] = original_cookie

            if original_other is None:
                os.environ.pop('SOME_OTHER_KEY', None)
            else:
                os.environ['SOME_OTHER_KEY'] = original_other

    def test_upsert_env_value_replaces_existing_cookie(self) -> None:
        updated_text, replaced = _upsert_env_value(
            'FOO=1\nWENCAI_COOKIE=stale\nBAR=2\n',
            key='WENCAI_COOKIE',
            value='Hexin-V=abc; THSSESSID=xyz',
        )

        self.assertTrue(replaced)
        self.assertEqual(updated_text, 'FOO=1\nWENCAI_COOKIE=Hexin-V=abc; THSSESSID=xyz\nBAR=2\n')

    def test_upsert_env_value_appends_cookie_when_missing(self) -> None:
        updated_text, replaced = _upsert_env_value(
            'FOO=1\nBAR=2\n',
            key='WENCAI_COOKIE',
            value='cookie=demo',
        )

        self.assertFalse(replaced)
        self.assertEqual(updated_text, 'FOO=1\nBAR=2\n\nWENCAI_COOKIE=cookie=demo\n')

    @patch('app.services.wencai_cookie_env._load_wencai_cookie_from_chrome')
    def test_sync_wencai_cookie_to_env_creates_env_from_template(self, mock_load_cookie) -> None:
        mock_load_cookie.return_value = ('Hexin-V=abc; THSSESSID=xyz', None)

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            template_path = root / '.env.example'
            env_path = root / '.env'
            template_path.write_text(
                'CORS_ALLOW_ORIGINS=http://localhost:5173\nWENCAI_COOKIE=your_browser_cookie_here\n',
                encoding='utf-8',
            )

            result = sync_wencai_cookie_to_env(env_path=env_path, template_path=template_path)

            self.assertTrue(result.created_env_file)
            self.assertTrue(result.updated_existing_key)
            self.assertEqual(result.env_path, env_path)
            self.assertIn('WENCAI_COOKIE=Hexin-V=abc; THSSESSID=xyz\n', env_path.read_text(encoding='utf-8'))
            self.assertIn('CORS_ALLOW_ORIGINS=http://localhost:5173\n', env_path.read_text(encoding='utf-8'))

    @patch('app.services.wencai_cookie_env._load_wencai_cookie_from_chrome')
    def test_sync_wencai_cookie_to_env_raises_when_cookie_unavailable(self, mock_load_cookie) -> None:
        mock_load_cookie.return_value = (None, '未能从 Chrome 中找到 iwencai / 10jqka 相关 Cookie。')

        with TemporaryDirectory() as tmpdir:
            env_path = Path(tmpdir) / '.env'
            with self.assertRaisesRegex(RuntimeError, '未能从 Chrome 中找到'):
                sync_wencai_cookie_to_env(env_path=env_path, template_path=None)
