from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Any, Iterator

from app.core.config import settings
from app.core.symbols import to_ts_code
from app.schemas.signal import SignalItem
from app.schemas.watchlist import WatchlistCreate, WatchlistItem


class LocalStore:
    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _init_db(self) -> None:
        with self._lock, self._connection() as connection:
            connection.executescript(
                '''
                CREATE TABLE IF NOT EXISTS watchlist (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    symbol TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    sector TEXT,
                    tags_json TEXT NOT NULL DEFAULT '[]',
                    note TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS market_snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_id INTEGER NOT NULL,
                    watchlist_id INTEGER NOT NULL,
                    symbol TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    score REAL NOT NULL,
                    confidence REAL NOT NULL,
                    action TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    reasons_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (snapshot_id) REFERENCES market_snapshots(id),
                    FOREIGN KEY (watchlist_id) REFERENCES watchlist(id)
                );

                CREATE INDEX IF NOT EXISTS idx_signals_snapshot_id ON signals(snapshot_id);
                CREATE INDEX IF NOT EXISTS idx_signals_watchlist_id ON signals(watchlist_id);
                CREATE INDEX IF NOT EXISTS idx_watchlist_symbol ON watchlist(symbol);

                CREATE TABLE IF NOT EXISTS wencai_jobs (
                    job_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    requested_query_count INTEGER NOT NULL DEFAULT 0,
                    executed_query_count INTEGER NOT NULL DEFAULT 0,
                    step_results_json TEXT NOT NULL DEFAULT '[]',
                    result_json TEXT,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    completed_at TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_wencai_jobs_status ON wencai_jobs(status);

                CREATE TABLE IF NOT EXISTS market_sentiment_points (
                    trade_date TEXT PRIMARY KEY,
                    rise_count INTEGER NOT NULL,
                    total_count INTEGER NOT NULL,
                    ratio REAL NOT NULL,
                    source TEXT NOT NULL,
                    note TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE INDEX IF NOT EXISTS idx_market_sentiment_points_trade_date
                ON market_sentiment_points(trade_date DESC);
                '''
            )

    @staticmethod
    def _now() -> str:
        return datetime.now().isoformat(timespec='seconds')

    @staticmethod
    def _row_to_watchlist(row: sqlite3.Row) -> WatchlistItem:
        return WatchlistItem(
            id=int(row['id']),
            symbol=row['symbol'],
            display_name=row['display_name'],
            sector=row['sector'],
            tags=json.loads(row['tags_json'] or '[]'),
            note=row['note'],
            created_at=row['created_at'],
            updated_at=row['updated_at'],
        )

    @staticmethod
    def _row_to_signal(row: sqlite3.Row) -> SignalItem:
        return SignalItem(
            id=int(row['id']),
            snapshot_id=int(row['snapshot_id']),
            watchlist_id=int(row['watchlist_id']),
            symbol=row['symbol'],
            display_name=row['display_name'],
            score=float(row['score']),
            confidence=float(row['confidence']),
            action=row['action'],
            summary=row['summary'],
            reasons=json.loads(row['reasons_json'] or '[]'),
            created_at=row['created_at'],
        )

    def list_watchlist(self) -> list[WatchlistItem]:
        with self._connection() as connection:
            rows = connection.execute(
                'SELECT * FROM watchlist ORDER BY updated_at DESC, id DESC'
            ).fetchall()
        return [self._row_to_watchlist(row) for row in rows]

    def add_watchlist_item(self, payload: WatchlistCreate) -> WatchlistItem:
        now = self._now()
        normalized_symbol = to_ts_code(payload.symbol)
        with self._lock, self._connection() as connection:
            existing_row = connection.execute(
                'SELECT * FROM watchlist WHERE symbol = ? ORDER BY id DESC LIMIT 1',
                (normalized_symbol,),
            ).fetchone()
            if existing_row:
                connection.execute(
                    'UPDATE watchlist SET updated_at = ? WHERE id = ?',
                    (now, int(existing_row['id'])),
                )
                row = connection.execute(
                    'SELECT * FROM watchlist WHERE id = ?',
                    (int(existing_row['id']),),
                ).fetchone()
                return self._row_to_watchlist(row)

            cursor = connection.execute(
                '''
                INSERT INTO watchlist(symbol, display_name, sector, tags_json, note, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    normalized_symbol,
                    payload.display_name.strip(),
                    payload.sector.strip() if payload.sector else None,
                    json.dumps([item.strip() for item in payload.tags if item.strip()], ensure_ascii=False),
                    payload.note.strip() if payload.note else None,
                    now,
                    now,
                ),
            )
            row = connection.execute(
                'SELECT * FROM watchlist WHERE id = ?',
                (cursor.lastrowid,),
            ).fetchone()
        return self._row_to_watchlist(row)

    def delete_watchlist_item(self, item_id: int) -> bool:
        with self._lock, self._connection() as connection:
            cursor = connection.execute('DELETE FROM watchlist WHERE id = ?', (item_id,))
        return cursor.rowcount > 0

    def record_snapshot(self, payload: dict[str, Any]) -> int:
        now = self._now()
        with self._lock, self._connection() as connection:
            cursor = connection.execute(
                'INSERT INTO market_snapshots(created_at, payload_json) VALUES (?, ?)',
                (now, json.dumps(payload, ensure_ascii=False)),
            )
        return int(cursor.lastrowid)

    def replace_signals(self, snapshot_id: int, signals: list[dict[str, Any]]) -> list[SignalItem]:
        now = self._now()
        with self._lock, self._connection() as connection:
            for signal in signals:
                connection.execute(
                    '''
                    INSERT INTO signals(
                        snapshot_id, watchlist_id, symbol, display_name, score, confidence,
                        action, summary, reasons_json, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (
                        snapshot_id,
                        signal['watchlist_id'],
                        signal['symbol'],
                        signal['display_name'],
                        signal['score'],
                        signal['confidence'],
                        signal['action'],
                        signal['summary'],
                        json.dumps(signal['reasons'], ensure_ascii=False),
                        now,
                    ),
                )

            rows = connection.execute(
                '''
                SELECT * FROM signals
                WHERE snapshot_id = ?
                ORDER BY score DESC, confidence DESC, id DESC
                ''',
                (snapshot_id,),
            ).fetchall()
        return [self._row_to_signal(row) for row in rows]

    def list_signals(self, limit: int = 20) -> list[SignalItem]:
        with self._connection() as connection:
            rows = connection.execute(
                '''
                SELECT * FROM signals
                ORDER BY created_at DESC, score DESC, id DESC
                LIMIT ?
                ''',
                (limit,),
            ).fetchall()
        return [self._row_to_signal(row) for row in rows]

    def latest_signal_for_watchlist(self, watchlist_id: int) -> SignalItem | None:
        with self._connection() as connection:
            row = connection.execute(
                '''
                SELECT * FROM signals
                WHERE watchlist_id = ?
                ORDER BY created_at DESC, score DESC, id DESC
                LIMIT 1
                ''',
                (watchlist_id,),
            ).fetchone()
        return self._row_to_signal(row) if row else None

    def upsert_market_sentiment_point(
        self,
        *,
        trade_date: str,
        rise_count: int,
        total_count: int,
        ratio: float,
        source: str,
        note: str | None = None,
        keep_latest: int = 5,
    ) -> dict[str, Any]:
        now = self._now()
        with self._lock, self._connection() as connection:
            existing = connection.execute(
                'SELECT trade_date, created_at FROM market_sentiment_points WHERE trade_date = ?',
                (trade_date,),
            ).fetchone()

            if existing:
                connection.execute(
                    '''
                    UPDATE market_sentiment_points
                    SET rise_count = ?, total_count = ?, ratio = ?, source = ?, note = ?, updated_at = ?
                    WHERE trade_date = ?
                    ''',
                    (rise_count, total_count, ratio, source, note, now, trade_date),
                )
                created_at = str(existing['created_at'])
            else:
                connection.execute(
                    '''
                    INSERT INTO market_sentiment_points(
                        trade_date, rise_count, total_count, ratio, source, note, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ''',
                    (trade_date, rise_count, total_count, ratio, source, note, now, now),
                )
                created_at = now

            if keep_latest > 0:
                connection.execute(
                    '''
                    DELETE FROM market_sentiment_points
                    WHERE trade_date NOT IN (
                        SELECT trade_date
                        FROM market_sentiment_points
                        ORDER BY trade_date DESC
                        LIMIT ?
                    )
                    ''',
                    (keep_latest,),
                )

        return {
            'trade_date': trade_date,
            'rise_count': rise_count,
            'total_count': total_count,
            'ratio': ratio,
            'source': source,
            'note': note,
            'created_at': created_at,
            'updated_at': now,
        }

    def list_market_sentiment_points(self, limit: int = 5) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                '''
                SELECT trade_date, rise_count, total_count, ratio, source, note, created_at, updated_at
                FROM market_sentiment_points
                ORDER BY trade_date DESC
                LIMIT ?
                ''',
                (limit,),
            ).fetchall()

        return [
            {
                'trade_date': str(row['trade_date']),
                'rise_count': int(row['rise_count']),
                'total_count': int(row['total_count']),
                'ratio': float(row['ratio']),
                'source': str(row['source']),
                'note': row['note'],
                'created_at': str(row['created_at']),
                'updated_at': str(row['updated_at']),
            }
            for row in rows
        ]

    def create_wencai_job(self, job_id: str, payload: dict[str, Any], requested_query_count: int) -> dict[str, Any]:
        now = self._now()
        with self._lock, self._connection() as connection:
            connection.execute(
                '''
                INSERT INTO wencai_jobs(
                    job_id, status, payload_json, requested_query_count, executed_query_count,
                    step_results_json, result_json, note, created_at, updated_at, started_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''',
                (
                    job_id,
                    'pending',
                    json.dumps(payload, ensure_ascii=False),
                    requested_query_count,
                    0,
                    '[]',
                    None,
                    '任务已创建，等待后台执行。',
                    now,
                    now,
                    None,
                    None,
                ),
            )
        return self.get_wencai_job(job_id) or {}

    def get_wencai_job(self, job_id: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                'SELECT * FROM wencai_jobs WHERE job_id = ?',
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            'job_id': row['job_id'],
            'status': row['status'],
            'payload': json.loads(row['payload_json'] or '{}'),
            'requested_query_count': int(row['requested_query_count'] or 0),
            'executed_query_count': int(row['executed_query_count'] or 0),
            'step_results': json.loads(row['step_results_json'] or '[]'),
            'result': json.loads(row['result_json']) if row['result_json'] else None,
            'note': row['note'],
            'created_at': row['created_at'],
            'updated_at': row['updated_at'],
            'started_at': row['started_at'],
            'completed_at': row['completed_at'],
        }

    def list_wencai_jobs_by_status(self, statuses: list[str]) -> list[dict[str, Any]]:
        if not statuses:
            return []
        placeholders = ','.join('?' for _ in statuses)
        with self._connection() as connection:
            rows = connection.execute(
                f'''
                SELECT * FROM wencai_jobs
                WHERE status IN ({placeholders})
                ORDER BY created_at ASC, job_id ASC
                ''',
                tuple(statuses),
            ).fetchall()
        return [
            {
                'job_id': row['job_id'],
                'status': row['status'],
                'payload': json.loads(row['payload_json'] or '{}'),
                'requested_query_count': int(row['requested_query_count'] or 0),
                'executed_query_count': int(row['executed_query_count'] or 0),
                'step_results': json.loads(row['step_results_json'] or '[]'),
                'result': json.loads(row['result_json']) if row['result_json'] else None,
                'note': row['note'],
                'created_at': row['created_at'],
                'updated_at': row['updated_at'],
                'started_at': row['started_at'],
                'completed_at': row['completed_at'],
            }
            for row in rows
        ]

    def start_wencai_job(self, job_id: str, note: str | None = None) -> dict[str, Any] | None:
        now = self._now()
        with self._lock, self._connection() as connection:
            connection.execute(
                '''
                UPDATE wencai_jobs
                SET status = ?, note = ?, updated_at = ?, started_at = COALESCE(started_at, ?)
                WHERE job_id = ?
                ''',
                ('running', note, now, now, job_id),
            )
        return self.get_wencai_job(job_id)

    def update_wencai_job_progress(
        self,
        job_id: str,
        *,
        executed_query_count: int,
        step_results: list[dict[str, Any]],
        note: str | None = None,
    ) -> dict[str, Any] | None:
        now = self._now()
        with self._lock, self._connection() as connection:
            connection.execute(
                '''
                UPDATE wencai_jobs
                SET status = ?, executed_query_count = ?, step_results_json = ?, note = ?, updated_at = ?
                WHERE job_id = ?
                ''',
                (
                    'running',
                    executed_query_count,
                    json.dumps(step_results, ensure_ascii=False),
                    note,
                    now,
                    job_id,
                ),
            )
        return self.get_wencai_job(job_id)

    def finish_wencai_job(
        self,
        job_id: str,
        *,
        status: str,
        executed_query_count: int,
        step_results: list[dict[str, Any]],
        result: dict[str, Any] | None,
        note: str | None = None,
    ) -> dict[str, Any] | None:
        now = self._now()
        with self._lock, self._connection() as connection:
            connection.execute(
                '''
                UPDATE wencai_jobs
                SET status = ?, executed_query_count = ?, step_results_json = ?, result_json = ?, note = ?, updated_at = ?, completed_at = ?
                WHERE job_id = ?
                ''',
                (
                    status,
                    executed_query_count,
                    json.dumps(step_results, ensure_ascii=False),
                    json.dumps(result, ensure_ascii=False) if result is not None else None,
                    note,
                    now,
                    now,
                    job_id,
                ),
            )
        return self.get_wencai_job(job_id)


_STORE: LocalStore | None = None


def get_local_store() -> LocalStore:
    global _STORE
    if _STORE is None:
        _STORE = LocalStore(Path(settings.sqlite_path))
    return _STORE
