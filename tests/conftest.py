import pytest

from app.guard import reset_limits
from app.qloo import CACHE


@pytest.fixture(autouse=True)
def clear_runtime_state(monkeypatch):
    for name in ("QLOO_API_KEY", "QLOO_BASELINE_VERIFIED", "OPENAI_API_KEY",
                 "RECEIPT_ALLOW_LLM_CALLS", "RECEIPT_LLM_MODEL",
                 "RECEIPT_LLM_DAILY_CALLS", "RECEIPT_QLOO_DAILY_CALLS"):
        monkeypatch.delenv(name, raising=False)
    reset_limits()
    CACHE.clear()
