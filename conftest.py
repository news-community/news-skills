"""Every test in this repository is offline unless LOCAL_NEWS_API_LIVE=1.

All HTTP(S), in this process and in any subprocess a test starts, is sent to a
closed local port, so a test that quietly needs the network fails rather than
passing on whatever the site said that day. The client's own suite has the same
guard inline (its tests also run from inside the skill folder); this one covers
`skills/meeting-prep`, `skills/cite-check` and `tests/`.
"""
import os

import pytest

LIVE_ENV = "LOCAL_NEWS_API_LIVE"
DEAD_PROXY = "http://127.0.0.1:9"


@pytest.fixture(autouse=True)
def _offline_everywhere(monkeypatch):
    if os.environ.get(LIVE_ENV):
        yield
        return
    for var in ("http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"):
        monkeypatch.setenv(var, DEAD_PROXY)
    for var in ("no_proxy", "NO_PROXY"):
        monkeypatch.delenv(var, raising=False)
    yield
