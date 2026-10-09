from fastapi.testclient import TestClient
from tenacity import wait_none

from insights.api import app, get_llm_client
from insights.resilience import ResilientLLMClient
from tests.fakes import EVENTS, VALID_RESPONSE, FakeLLMClient


def client_with(fake):
    app.dependency_overrides[get_llm_client] = lambda: ResilientLLMClient(fake, wait=wait_none())
    return TestClient(app)


def teardown_function():
    app.dependency_overrides.clear()


def test_returns_insight():
    response = client_with(FakeLLMClient(VALID_RESPONSE)).post("/teams/platform/insights", json={"events": EVENTS})
    assert response.status_code == 200
    assert response.json()["metrics"]["merged_prs"] == 1


def test_returns_422_for_malformed_event():
    events = [{"type": "pr_opened", "timestamp": "2026-01-01T09:00:00Z"}]
    response = client_with(FakeLLMClient(VALID_RESPONSE)).post("/teams/platform/insights", json={"events": events})
    assert response.status_code == 422


def test_returns_502_for_invalid_llm_output():
    response = client_with(FakeLLMClient("not json")).post("/teams/platform/insights", json={"events": EVENTS})
    assert response.status_code == 502


def test_returns_503_when_llm_is_unavailable():
    response = client_with(FakeLLMClient(TimeoutError())).post("/teams/platform/insights", json={"events": EVENTS})
    assert response.status_code == 503
