import pytest

from insights.core import InvalidEvent, InvalidLLMResponse, build_prompt, calculate_metrics, parse_llm_response
from tests.fakes import EVENTS


def test_calculates_metrics_from_example():
    assert calculate_metrics(EVENTS) == {
        "merged_prs": 1,
        "average_pr_cycle_time_hours": 24.0,
        "deployments": 1,
        "incidents": 1,
    }


def test_ignores_unmatched_pull_requests_for_cycle_time():
    events = [
        {"type": "pr_opened", "id": "pr-1", "timestamp": "2026-01-01T09:00:00Z"},
        {"type": "pr_merged", "id": "pr-2", "timestamp": "2026-01-02T09:00:00Z"},
    ]
    metrics = calculate_metrics(events)
    assert metrics["merged_prs"] == 1
    assert metrics["average_pr_cycle_time_hours"] is None


def test_averages_multiple_pull_requests():
    events = [
        {"type": "pr_opened", "id": "a", "timestamp": "2026-01-01T00:00:00Z"},
        {"type": "pr_merged", "id": "a", "timestamp": "2026-01-01T10:00:00Z"},
        {"type": "pr_opened", "id": "b", "timestamp": "2026-01-01T00:00:00Z"},
        {"type": "pr_merged", "id": "b", "timestamp": "2026-01-01T20:00:00Z"},
    ]
    assert calculate_metrics(events)["average_pr_cycle_time_hours"] == 15.0


@pytest.mark.parametrize(
    "event",
    [
        "not-a-dict",
        {"type": "unknown", "timestamp": "2026-01-01T09:00:00Z"},
        {"type": "pr_opened", "timestamp": "2026-01-01T09:00:00Z"},
        {"type": "deployment", "timestamp": "2026-01-01T09:00:00"},
        {"type": "deployment", "timestamp": "yesterday"},
    ],
)
def test_rejects_malformed_events(event):
    with pytest.raises(InvalidEvent):
        calculate_metrics([event])


def test_prompt_contains_only_aggregated_metrics():
    prompt = build_prompt("platform", calculate_metrics(EVENTS))
    assert "pr-1" not in prompt
    assert "2026-01-01" not in prompt
    assert '"merged_prs": 1' in prompt


@pytest.mark.parametrize(
    "raw",
    [
        "not json",
        "[]",
        '{"summary": 1, "recommendations": []}',
        '{"summary": "ok", "recommendations": "not a list"}',
        '{"summary": "ok", "recommendations": [1, 2]}',
    ],
)
def test_rejects_invalid_llm_responses(raw):
    with pytest.raises(InvalidLLMResponse):
        parse_llm_response(raw)
