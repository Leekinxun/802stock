#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / 'backend'

if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.wencai_cookie_env import sync_wencai_cookie_to_env


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description='从本机 Chrome 读取问财 Cookie，并写入项目 .env。')
    parser.add_argument(
        '--env-file',
        default=str(PROJECT_ROOT / '.env'),
        help='目标 .env 文件路径，默认写入项目根目录 .env',
    )
    parser.add_argument(
        '--template-file',
        default=str(PROJECT_ROOT / '.env.example'),
        help='当 .env 不存在时，用来初始化内容的模板文件路径',
    )
    args = parser.parse_args(argv)

    try:
        result = sync_wencai_cookie_to_env(
            env_path=Path(args.env_file).expanduser(),
            template_path=Path(args.template_file).expanduser(),
        )
    except RuntimeError as exc:
        print(f'写入失败：{exc}', file=sys.stderr)
        return 1

    action = '更新' if result.updated_existing_key else '写入'
    created_hint = '（已基于模板创建 .env）' if result.created_env_file else ''

    print(f'已{action} WENCAI_COOKIE 到 {result.env_path}{created_hint}')
    print('如后端已在运行，请重启服务后再发起问财请求。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
