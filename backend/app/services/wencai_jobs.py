from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from threading import Lock
from uuid import uuid4

from app.schemas.market import (
    WencaiIntersectionJobCreateResponse,
    WencaiIntersectionJobResponse,
    WencaiIntersectionRequest,
    WencaiIntersectionResponse,
    WencaiIntersectionStepResult,
)
from app.services.local_store import get_local_store
from app.services.wencai import run_wencai_intersection

_EXECUTOR = ThreadPoolExecutor(max_workers=2, thread_name_prefix='wencai-job')
_RUNNING_JOB_IDS: set[str] = set()
_RUNNING_LOCK = Lock()


def _job_to_response(payload: dict) -> WencaiIntersectionJobResponse:
    step_results = [
        WencaiIntersectionStepResult.model_validate(item)
        for item in payload.get('step_results', [])
    ]
    result_payload = payload.get('result')
    result = WencaiIntersectionResponse.model_validate(result_payload) if result_payload else None

    return WencaiIntersectionJobResponse(
        job_id=str(payload.get('job_id') or ''),
        status=str(payload.get('status') or 'pending'),
        created_at=str(payload.get('created_at') or ''),
        updated_at=str(payload.get('updated_at') or ''),
        started_at=payload.get('started_at'),
        completed_at=payload.get('completed_at'),
        requested_query_count=int(payload.get('requested_query_count') or 0),
        executed_query_count=int(payload.get('executed_query_count') or 0),
        step_results=step_results,
        note=payload.get('note'),
        result=result,
    )


def create_wencai_intersection_job(payload: WencaiIntersectionRequest) -> WencaiIntersectionJobCreateResponse:
    normalized_queries = [query.strip() for query in payload.queries if query.strip()]
    job_id = uuid4().hex
    store = get_local_store()
    job_record = store.create_wencai_job(
        job_id,
        payload.model_dump(),
        requested_query_count=len(normalized_queries),
    )
    submit_wencai_job(job_id)
    return WencaiIntersectionJobCreateResponse(
        job_id=job_id,
        status=str(job_record.get('status') or 'pending'),
        created_at=str(job_record.get('created_at') or ''),
        requested_query_count=int(job_record.get('requested_query_count') or len(normalized_queries)),
        poll_after_seconds=5,
        note=job_record.get('note'),
    )


def get_wencai_intersection_job(job_id: str) -> WencaiIntersectionJobResponse | None:
    payload = get_local_store().get_wencai_job(job_id)
    if payload is None:
        return None
    return _job_to_response(payload)


def submit_wencai_job(job_id: str) -> None:
    with _RUNNING_LOCK:
        if job_id in _RUNNING_JOB_IDS:
            return
        _RUNNING_JOB_IDS.add(job_id)

    _EXECUTOR.submit(_run_wencai_job, job_id)


def recover_wencai_jobs() -> None:
    for job in get_local_store().list_wencai_jobs_by_status(['pending', 'running']):
        submit_wencai_job(str(job.get('job_id') or ''))


def _run_wencai_job(job_id: str) -> None:
    store = get_local_store()
    try:
        job = store.get_wencai_job(job_id)
        if job is None:
            return

        payload = WencaiIntersectionRequest.model_validate(job.get('payload') or {})
        store.start_wencai_job(job_id, note='后台任务已启动，开始执行问财交集。')

        def _progress_callback(
            executed_query_count: int,
            _total_queries: int,
            step_results: list[WencaiIntersectionStepResult],
            note: str,
        ) -> None:
            store.update_wencai_job_progress(
                job_id,
                executed_query_count=executed_query_count,
                step_results=[item.model_dump() for item in step_results],
                note=note,
            )

        result = run_wencai_intersection(
            queries=payload.queries,
            sort_key=payload.sort_key,
            sort_order=payload.sort_order,
            limit=payload.limit,
            query_type=payload.query_type,
            interval_seconds=payload.interval_seconds,
            import_to_watchlist=payload.import_to_watchlist,
            progress_callback=_progress_callback,
        )

        final_status = 'succeeded' if result.supported else 'failed'
        store.finish_wencai_job(
            job_id,
            status=final_status,
            executed_query_count=result.executed_query_count,
            step_results=[item.model_dump() for item in result.step_results],
            result=result.model_dump(),
            note=result.note,
        )
    except Exception as exc:
        failed_job = store.get_wencai_job(job_id)
        step_results = failed_job.get('step_results', []) if failed_job else []
        executed_query_count = int(failed_job.get('executed_query_count') or 0) if failed_job else 0
        store.finish_wencai_job(
            job_id,
            status='failed',
            executed_query_count=executed_query_count,
            step_results=step_results,
            result=None,
            note=f'后台任务异常失败：{exc}',
        )
    finally:
        with _RUNNING_LOCK:
            _RUNNING_JOB_IDS.discard(job_id)
