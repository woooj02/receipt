"""Small, bounded background queue for long audits and captured-output reports."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event, RLock
import secrets
import time
import logging

from .runtime import WorkTimeout, work_budget


class QueueFull(RuntimeError):
    pass


class JobStore:
    def __init__(self):
        self.lock = RLock()
        self.items = {}
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="receipt")

    def submit(self, owner, fn):
        with self.lock:
            self._prune()
            active = [job for job in self.items.values() if job["status"] in ("queued", "running")]
            if any(job["owner"] == owner for job in active):
                raise QueueFull("A run is already active in this browser. Cancel or finish it first.")
            if len(active) >= 4:
                raise QueueFull("The work queue is full. Please try again shortly.")
            job_id = secrets.token_urlsafe(18)
            self.items[job_id] = {"job_id": job_id, "owner": owner, "status": "queued",
                                  "phase": "Waiting for a worker", "created": time.time(),
                                  "result": None, "error": None, "cancel": Event()}
            self.pool.submit(self._run, job_id, fn)
            return self.get(job_id, owner)

    def _run(self, job_id, fn):
        with self.lock:
            job = self.items[job_id]
            job["status"] = "running"
        def update(phase):
            with self.lock:
                job["phase"] = phase
        try:
            with work_budget(180, update, job["cancel"]):
                result = fn()
                from .runtime import remaining
                remaining()
            with self.lock:
                job.update(status="complete", phase="Complete", result=result)
        except Exception as exc:
            from .agent import AgentError
            from .qloo import QlooError
            from .receipt import AuditError
            from .guard import CapacityError
            expected = isinstance(exc, (WorkTimeout, AgentError, QlooError, AuditError, CapacityError))
            if not expected:
                logging.getLogger(__name__).exception("Unexpected background job failure")
            public = str(exc) if expected else "This run could not complete. Please retry."
            with self.lock:
                job.update(status="cancelled" if job["cancel"].is_set() else "error",
                           phase="Stopped", error=public)

    def get(self, job_id, owner):
        with self.lock:
            self._prune()
            job = self.items.get(job_id)
            if not job or job["owner"] != owner:
                raise KeyError("Job not found in this session.")
            return deepcopy({key: value for key, value in job.items() if key not in ("owner", "cancel")})

    def cancel(self, job_id, owner):
        with self.lock:
            self.get(job_id, owner)
            self.items[job_id]["cancel"].set()
            return {"cancel_requested": True}

    def _prune(self):
        now = time.time()
        for job_id, job in list(self.items.items()):
            if job["status"] not in ("queued", "running") and job["created"] + 1800 < now:
                self.items.pop(job_id)
        completed = [job_id for job_id, job in self.items.items() if job["status"] not in ("queued", "running")]
        while len(self.items) > 200 and completed:
            self.items.pop(completed.pop(0))


JOBS = JobStore()
