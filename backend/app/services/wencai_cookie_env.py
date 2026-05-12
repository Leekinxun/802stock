from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.core.config import PROJECT_ROOT
from app.services.wencai import _load_wencai_cookie_from_chrome

WENCAI_COOKIE_ENV_KEY = 'WENCAI_COOKIE'


@dataclass(slots=True)
class WencaiCookieEnvSyncResult:
    env_path: Path
    created_env_file: bool
    updated_existing_key: bool
    cookie_length: int


def _read_seed_env_text(env_path: Path, template_path: Path | None) -> tuple[str, bool]:
    if env_path.exists():
        return env_path.read_text(encoding='utf-8'), False

    if template_path is not None and template_path.exists():
        return template_path.read_text(encoding='utf-8'), True

    return '', True


def _upsert_env_value(env_text: str, *, key: str, value: str) -> tuple[str, bool]:
    pattern = re.compile(rf'^\s*(?:export\s+)?{re.escape(key)}\s*=')
    replacement = f'{key}={value}'

    lines = env_text.splitlines()
    replaced = False
    updated_lines: list[str] = []

    for line in lines:
        if pattern.match(line):
            updated_lines.append(replacement)
            replaced = True
            continue
        updated_lines.append(line)

    if not replaced:
        if updated_lines and updated_lines[-1].strip():
            updated_lines.append('')
        updated_lines.append(replacement)

    updated_text = '\n'.join(updated_lines)
    if updated_text and not updated_text.endswith('\n'):
        updated_text += '\n'

    return updated_text, replaced


def sync_wencai_cookie_to_env(
    env_path: Path | None = None,
    *,
    template_path: Path | None = None,
) -> WencaiCookieEnvSyncResult:
    cookie, error = _load_wencai_cookie_from_chrome()
    if not cookie:
        raise RuntimeError(error or '未能从 Chrome 中读取问财 Cookie。')

    resolved_env_path = env_path or (PROJECT_ROOT / '.env')
    resolved_template_path = template_path if template_path is not None else (PROJECT_ROOT / '.env.example')

    env_text, created_env_file = _read_seed_env_text(resolved_env_path, resolved_template_path)
    updated_text, updated_existing_key = _upsert_env_value(
        env_text,
        key=WENCAI_COOKIE_ENV_KEY,
        value=cookie,
    )

    resolved_env_path.parent.mkdir(parents=True, exist_ok=True)
    resolved_env_path.write_text(updated_text, encoding='utf-8')

    return WencaiCookieEnvSyncResult(
        env_path=resolved_env_path,
        created_env_file=created_env_file,
        updated_existing_key=updated_existing_key,
        cookie_length=len(cookie),
    )
