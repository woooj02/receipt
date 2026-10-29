"""Body, concurrency and per-address work limits for the public demo."""

from collections import OrderedDict, deque
from contextlib import contextmanager
from datetime import datetime, timezone
import json
import os
from threading import RLock, BoundedSemaphore
import time


class CapacityError(RuntimeError):
    pass


_SLOTS = BoundedSemaphore(2)
_LOCK = RLock()
_USAGE = {}
_ADDRESSES = OrderedDict()
MAX_BODY = 131072


@contextmanager
def work_slot():
    if not _SLOTS.acquire(blocking=False):
        raise CapacityError("Both workers are busy. Please try again shortly.")
    try:
        yield
    finally:
        _SLOTS.release()


def reserve_provider(kind):
    day = datetime.now(timezone.utc).date().isoformat()
    limit = int(os.environ.get("RECEIPT_LLM_DAILY_CALLS", "20")) if kind == "llm" else int(os.environ.get("RECEIPT_QLOO_DAILY_CALLS", "1500"))
    with _LOCK:
        key = (day, kind)
        if _USAGE.get(key, 0) >= limit:
            raise CapacityError("The demo's daily provider-call allowance has been reached.")
        _USAGE[key] = _USAGE.get(key, 0) + 1
        for old in list(_USAGE):
            if old[0] != day:
                _USAGE.pop(old)


def reset_limits():
    with _LOCK:
        _ADDRESSES.clear()
        _USAGE.clear()


class RequestGuard:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or not scope["path"].startswith("/api/"):
            return await self.app(scope, receive, send)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > MAX_BODY:
                return await self._reject(send, 413, "Request is too large.")
            if not message.get("more_body"):
                break
        weight = 1
        try:
            payload = json.loads(body)
            payload = payload.get("payload", payload) if isinstance(payload, dict) else {}
            if isinstance(payload, dict) and isinstance(payload.get("profiles"), list):
                weight = max(1, min(20, len(payload["profiles"])))
        except (ValueError, UnicodeError):
            pass
        address = (scope.get("client") or ("unknown",))[0]
        now = time.monotonic()
        with _LOCK:
            records = _ADDRESSES.setdefault(address, deque())
            while records and records[0][0] <= now - 60:
                records.popleft()
            blocked = sum(item[1] for item in records) + weight > 60
            if not blocked:
                records.append((now, weight))
                _ADDRESSES.move_to_end(address)
                while len(_ADDRESSES) > 4096:
                    _ADDRESSES.popitem(last=False)
        if blocked:
            return await self._reject(send, 429, "Too many requests. Try again in a minute.")
        consumed = False
        async def replay():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()
        await self.app(scope, replay, send)

    @staticmethod
    async def _reject(send, status, message):
        body = json.dumps({"detail": message}).encode()
        headers = [(b"content-type", b"application/json"), (b"cache-control", b"no-store")]
        if status == 429:
            headers.append((b"retry-after", b"60"))
        await send({"type": "http.response.start", "status": status, "headers": headers})
        await send({"type": "http.response.body", "body": body})
