from dataclasses import dataclass, field
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
BACKEND_ROOT = Path(__file__).resolve().parents[2]
DOTENV_OVERRIDE_KEYS = {'WENCAI_COOKIE'}


def _load_dotenv(dotenv_path: Path) -> None:
    """Load simple KEY=VALUE pairs from .env.

    Most keys keep the traditional "process env wins" behavior, but a small
    allowlist can intentionally be forced from the project .env so repo-local
    runtime secrets are preferred over stale shell/session exports.
    """
    if not dotenv_path.exists():
        return

    for raw_line in dotenv_path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#'):
            continue

        if line.startswith('export '):
            line = line[len('export '):].strip()

        if '=' not in line:
            continue

        key, value = line.split('=', 1)
        key = key.strip()
        value = value.strip()

        if not key:
            continue

        if value and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]

        if key in DOTENV_OVERRIDE_KEYS:
            os.environ[key] = value
        else:
            os.environ.setdefault(key, value)


def _resolve_project_path(raw_value: str | None, default_path: Path) -> str:
    if not raw_value:
        return str(default_path)

    path = Path(raw_value).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return str(path)


_load_dotenv(PROJECT_ROOT / '.env')


@dataclass(slots=True)
class Settings:
    app_name: str = 'STOCK Quant Platform API'
    app_version: str = '0.1.0'
    api_prefix: str = '/api/v1'
    runtime_dir: str = field(
        default_factory=lambda: _resolve_project_path(
            os.getenv('QUANT_RUNTIME_DIR'),
            BACKEND_ROOT / '.runtime',
        )
    )
    sqlite_path: str = field(
        default_factory=lambda: _resolve_project_path(
            os.getenv('QUANT_SQLITE_PATH'),
            BACKEND_ROOT / '.runtime' / 'quant_platform.db',
        )
    )
    allow_origins: list[str] = field(
        default_factory=lambda: [
            origin.strip()
            for origin in os.getenv('CORS_ALLOW_ORIGINS', 'http://localhost:5173,http://127.0.0.1:5173').split(',')
            if origin.strip()
        ]
    )


settings = Settings()
