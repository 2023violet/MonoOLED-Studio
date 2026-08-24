from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from threading import Event, Lock, Thread
import time
from typing import Callable


class AutomationJobCancelled(RuntimeError):
    pass


@dataclass
class AutomationJob:
    id: str
    operation: str
    arguments: dict
    snapshot: dict
    state: str = 'queued'
    stage: str = 'queued'
    completed: int = 0
    total: int = 0
    started_at: float | None = None
    finished_at: float | None = None
    result: dict | None = None
    error: dict | None = None
    cancel_requested: bool = False
    cancel_event: Event = field(default_factory=Event)


class AutomationJobManager:
    """Small server-owned job registry for long deterministic Automation calls.

    Jobs run against a deep-copied scene snapshot supplied at start time, so
    status/result calls never contend with the live editor's automation lock and
    a later GUI edit cannot silently change the job's input contract.
    """

    def __init__(self):
        self._lock = Lock()
        self._seq = 0
        self._jobs: dict[str, AutomationJob] = {}

    def start(self, operation: str, arguments: dict, snapshot: dict, runner: Callable) -> str:
        with self._lock:
            self._seq += 1
            jid = f'job-{self._seq}'
            job = AutomationJob(jid, str(operation), deepcopy(arguments), deepcopy(snapshot))
            self._jobs[jid] = job
        thread = Thread(target=self._run, args=(job, runner), name=f'MonoOLED-{jid}', daemon=True)
        thread.start()
        return jid

    def _run(self, job: AutomationJob, runner: Callable) -> None:
        with self._lock:
            job.state = 'running'
            job.stage = 'starting'
            job.started_at = time.monotonic()

        def progress(stage: str, completed: int, total: int) -> None:
            with self._lock:
                job.stage = str(stage)
                job.completed = max(0, int(completed))
                job.total = max(0, int(total))
            if job.cancel_event.is_set():
                raise AutomationJobCancelled('job cancellation requested')

        try:
            result = runner(job.operation, deepcopy(job.arguments), deepcopy(job.snapshot), progress, job.cancel_event)
            if job.cancel_event.is_set():
                raise AutomationJobCancelled('job cancellation requested')
            with self._lock:
                job.result = deepcopy(result)
                job.state = 'completed'
                job.stage = 'completed'
                if job.total <= 0:
                    job.total = 1
                job.completed = job.total
        except AutomationJobCancelled as exc:
            with self._lock:
                job.state = 'cancelled'
                job.stage = 'cancelled'
                job.error = {'code': 'CANCELLED', 'message': str(exc)}
        except Exception as exc:  # job boundary must preserve error evidence
            with self._lock:
                job.state = 'failed'
                job.stage = 'failed'
                job.error = {'code': type(exc).__name__, 'message': str(exc)}
        finally:
            with self._lock:
                job.finished_at = time.monotonic()

    def _get(self, job_id: str) -> AutomationJob:
        with self._lock:
            try:
                return self._jobs[str(job_id)]
            except KeyError:
                raise KeyError(f'unknown job id: {job_id}')

    def status(self, job_id: str) -> dict:
        with self._lock:
            if str(job_id) not in self._jobs:
                raise KeyError(f'unknown job id: {job_id}')
            job = self._jobs[str(job_id)]
            total = int(job.total)
            completed = int(job.completed)
            percent = 100.0 if job.state == 'completed' else (0.0 if total <= 0 else min(100.0, completed * 100.0 / total))
            elapsed = 0.0
            if job.started_at is not None:
                end = job.finished_at if job.finished_at is not None else time.monotonic()
                elapsed = max(0.0, end - job.started_at)
            return {
                'job_id': job.id,
                'operation': job.operation,
                'state': job.state,
                'stage': job.stage,
                'progress': {'completed': completed, 'total': total, 'percent': percent},
                'elapsed_ms': int(round(elapsed * 1000.0)),
                'cancel_requested': bool(job.cancel_requested),
                'error': deepcopy(job.error),
            }

    def result(self, job_id: str) -> dict:
        with self._lock:
            if str(job_id) not in self._jobs:
                raise KeyError(f'unknown job id: {job_id}')
            job = self._jobs[str(job_id)]
            return {
                'job_id': job.id,
                'operation': job.operation,
                'state': job.state,
                'result': deepcopy(job.result),
                'error': deepcopy(job.error),
            }

    def cancel(self, job_id: str) -> dict:
        with self._lock:
            if str(job_id) not in self._jobs:
                raise KeyError(f'unknown job id: {job_id}')
            job = self._jobs[str(job_id)]
            if job.state in {'completed', 'failed', 'cancelled'}:
                return {'job_id': job.id, 'state': job.state, 'cancel_requested': False}
            job.cancel_requested = True
            job.cancel_event.set()
            return {'job_id': job.id, 'state': job.state, 'cancel_requested': True}
