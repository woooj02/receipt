"""Bounded private caching and cooperative deadlines for provider work."""

from collections import OrderedDict
from contextlib import contextmanager
from contextvars import ContextVar
from copy import deepcopy
from threading import RLock
import time


class WorkTimeout(RuntimeError):
    pass


_DEADLINE = ContextVar("receipt_deadline", default=None)
_PROGRESS = ContextVar("receipt_progress", default=None)
_CANCEL = ContextVar("receipt_cancel", default=None)


def remaining(default=15):
    deadline = _DEADLINE.get()
    if _CANCEL.get() and _CANCEL.get().is_set():
        raise WorkTimeout("This run was cancelled.")
    if deadline is None:
        return default
    left = deadline - time.monotonic()
    if left <= 0:
        raise WorkTimeout("This run reached its time limit.")
    return min(default, left)


def progress(message):
    remaining()
    callback = _PROGRESS.get()
    if callback:
        callback(message)


@contextmanager
def work_budget(seconds=180, callback=None, cancellation=None):
    existing = _DEADLINE.get()
    tokens = (_DEADLINE.set(min(existing, time.monotonic() + seconds) if existing else time.monotonic() + seconds),
              _PROGRESS.set(callback or _PROGRESS.get()), _CANCEL.set(cancellation or _CANCEL.get()))
    try:
        remaining()
        yield
    finally:
        _DEADLINE.reset(tokens[0])
        _PROGRESS.reset(tokens[1])
        _CANCEL.reset(tokens[2])


class PrivateCache:
    def __init__(self, capacity=512, ttl=300):
        self.capacity, self.ttl = capacity, ttl
        self.items = OrderedDict()
        self.lock = RLock()

    def get(self, key):
        with self.lock:
            item = self.items.get(key)
            if item is None:
                return None
            deadline, value = item
            if deadline <= time.monotonic():
                self.items.pop(key, None)
                return None
            self.items.move_to_end(key)
            return deepcopy(value)

    def put(self, key, value):
        with self.lock:
            self.items[key] = (time.monotonic() + self.ttl, deepcopy(value))
            self.items.move_to_end(key)
            while len(self.items) > self.capacity:
                self.items.popitem(last=False)

    def clear(self):
        with self.lock:
            self.items.clear()
