from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from app.core.config import PROJECT_ROOT

TS_CODE_PATTERN = re.compile(r'^(?P<digits>\d{5,6})\.(?P<exchange>SH|SZ|BJ|HK)$', re.IGNORECASE)
PREFIX_CODE_PATTERN = re.compile(r'^(?P<exchange>SH|SZ|BJ|HK)(?P<digits>\d{5,6})$', re.IGNORECASE)
DIGITS_PATTERN = re.compile(r'^\d{5,6}$')


@dataclass(frozen=True, slots=True)
class ResolvedSymbol:
    digits: str
    exchange: str

    @property
    def ts_code(self) -> str:
        return f'{self.digits}.{self.exchange}'

    @property
    def stockapi_code(self) -> str:
        return f'{self.exchange}{self.digits}'

    @property
    def tencent_code(self) -> str:
        return f'{self.exchange.lower()}{self.digits}'


def _candidate_codename_paths() -> list[Path]:
    candidates: list[Path] = []
    env_path = os.getenv('CODENAME_CSV_PATH')
    if env_path:
        candidates.append(Path(env_path).expanduser())

    candidates.extend([
        PROJECT_ROOT / 'codename.csv',
        PROJECT_ROOT.parent / 'codename.csv',
    ])

    unique: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        if path not in seen:
            unique.append(path)
            seen.add(path)
    return unique


@lru_cache(maxsize=1)
def _load_codename_index() -> tuple[dict[str, str], dict[str, str], dict[str, str]]:
    by_ts_code: dict[str, str] = {}
    by_symbol: dict[str, str] = {}
    by_name: dict[str, str] = {}

    for path in _candidate_codename_paths():
        if not path.exists():
            continue

        with path.open('r', encoding='utf-8-sig', newline='') as file_obj:
            for row in csv.DictReader(file_obj):
                ts_code = str(row.get('ts_code') or '').strip().upper()
                digits = str(row.get('symbol') or '').strip()
                name = str(row.get('name') or '').strip()

                if not ts_code or '.' not in ts_code:
                    continue

                by_ts_code.setdefault(ts_code, ts_code)
                if digits:
                    by_symbol.setdefault(digits, ts_code)
                if name:
                    by_name.setdefault(name.lower(), ts_code)

        break

    return by_ts_code, by_symbol, by_name


def _infer_exchange_from_digits(digits: str) -> str:
    if len(digits) == 5:
        return 'HK'
    if digits.startswith(('5', '6', '9')):
        return 'SH'
    if digits.startswith(('4', '8')):
        return 'BJ'
    return 'SZ'


def _resolve_from_ts_code(ts_code: str) -> ResolvedSymbol | None:
    match = TS_CODE_PATTERN.match(ts_code.strip().upper())
    if not match:
        return None
    return ResolvedSymbol(
        digits=match.group('digits'),
        exchange=match.group('exchange').upper(),
    )


def _resolve_from_prefixed_code(symbol: str) -> ResolvedSymbol | None:
    match = PREFIX_CODE_PATTERN.match(symbol.strip().upper())
    if not match:
        return None
    return ResolvedSymbol(
        digits=match.group('digits'),
        exchange=match.group('exchange').upper(),
    )


def resolve_symbol(symbol: str) -> ResolvedSymbol | None:
    raw = (symbol or '').strip()
    if not raw:
        return None

    resolved = _resolve_from_ts_code(raw)
    if resolved:
        return resolved

    resolved = _resolve_from_prefixed_code(raw)
    if resolved:
        return resolved

    upper_raw = raw.upper()
    by_ts_code, by_symbol, by_name = _load_codename_index()

    if upper_raw in by_ts_code:
        return _resolve_from_ts_code(by_ts_code[upper_raw])

    compact = upper_raw.replace(' ', '')
    if compact in by_ts_code:
        return _resolve_from_ts_code(by_ts_code[compact])

    if DIGITS_PATTERN.match(raw):
        looked_up = by_symbol.get(raw)
        if looked_up:
            return _resolve_from_ts_code(looked_up)
        return ResolvedSymbol(digits=raw, exchange=_infer_exchange_from_digits(raw))

    looked_up = by_name.get(raw.lower())
    if looked_up:
        return _resolve_from_ts_code(looked_up)

    digits = ''.join(ch for ch in raw if ch.isdigit())
    if DIGITS_PATTERN.match(digits):
        looked_up = by_symbol.get(digits)
        if looked_up:
            return _resolve_from_ts_code(looked_up)
        return ResolvedSymbol(digits=digits, exchange=_infer_exchange_from_digits(digits))

    return None


def to_ts_code(symbol: str) -> str:
    raw = (symbol or '').strip()
    resolved = resolve_symbol(raw)
    return resolved.ts_code if resolved else raw.upper()


def to_stockapi_code(symbol: str) -> str:
    raw = (symbol or '').strip()
    resolved = resolve_symbol(raw)
    return resolved.stockapi_code if resolved else raw.upper()


def to_tencent_code(symbol: str) -> str:
    raw = (symbol or '').strip()
    resolved = resolve_symbol(raw)
    return resolved.tencent_code if resolved else raw.lower()


def symbol_aliases(symbol: str) -> set[str]:
    raw = (symbol or '').strip()
    aliases: set[str] = set()
    if raw:
        aliases.update({raw, raw.upper(), raw.lower()})

    resolved = resolve_symbol(raw)
    if not resolved:
        return {alias for alias in aliases if alias}

    aliases.update(
        {
            resolved.digits,
            resolved.ts_code,
            resolved.stockapi_code,
            resolved.stockapi_code.lower(),
            resolved.tencent_code,
            resolved.tencent_code.upper(),
            f'{resolved.digits}.{resolved.exchange.lower()}',
        }
    )
    return {alias for alias in aliases if alias}
