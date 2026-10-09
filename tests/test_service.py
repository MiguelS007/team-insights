import pytest
from tenacity import wait_none

from insights.core import InvalidEvent, InvalidLLMResponse
from insights.resilience import ResilientLLMClient
from insights.service import generate_team_insight
from tests.fakes import EVENTS, VALID_RESPONSE, FakeLLMClient


def test_returns_structured_insight():
    result = generate_team_insight("platform", EVENTS, FakeLLMClient(VALID_RESPONSE))
    assert result == {
        "team_id": "platform",
        "metrics": {
            "merged_prs": 1,
            "average_pr_cycle_time_hours": 24.0,
            "deployments": 1,
            "incidents": 1,
        },
        "insight": {
            "summary": "Healthy delivery flow.",
            "recommendations": ["Monitor cycle time."],
        },
    }


def test_does_not_call_llm_when_events_are_invalid():
    fake = FakeLLMClient(VALID_RESPONSE)
    with pytest.raises(InvalidEvent):
        generate_team_insight("platform", [{"type": "deployment"}], fake)
    assert fake.prompts == []


def test_rejects_invalid_llm_output_without_retrying():
    fake = FakeLLMClient("not json")
    client = ResilientLLMClient(fake, wait=wait_none())
    with pytest.raises(InvalidLLMResponse):
        generate_team_insight("platform", EVENTS, client)
    assert len(fake.prompts) == 1


@pytest.mark.parametrize("team_id", ["", "   ", None])
def test_rejects_invalid_team_id(team_id):
    with pytest.raises(ValueError):
        generate_team_insight(team_id, EVENTS, FakeLLMClient(VALID_RESPONSE))
