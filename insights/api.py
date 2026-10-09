from __future__ import annotations

from typing import Any, Literal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel

from insights.core import InvalidEvent, InvalidLLMResponse, LLMClient
from insights.resilience import LLMUnavailable, ResilientLLMClient
from insights.service import generate_team_insight


class Event(BaseModel):
    type: Literal["pr_opened", "pr_merged", "deployment", "incident"]
    timestamp: str
    id: str | None = None


class InsightRequest(BaseModel):
    events: list[Event]


class Insight(BaseModel):
    summary: str
    recommendations: list[str]


class InsightResponse(BaseModel):
    team_id: str
    metrics: dict[str, Any]
    insight: Insight


class StubLLMClient:
    def complete(self, prompt: str, timeout_seconds: float) -> str:
        return '{"summary": "Stub insight.", "recommendations": ["Connect a real LLM provider."]}'


_llm_client = ResilientLLMClient(StubLLMClient(), name="stub-llm")


def get_llm_client() -> LLMClient:
    return _llm_client


app = FastAPI(title="Team Insights")


@app.post("/teams/{team_id}/insights", response_model=InsightResponse)
def create_team_insight(
    team_id: str,
    request: InsightRequest,
    llm_client: LLMClient = Depends(get_llm_client),
) -> dict[str, Any]:
    events = [event.model_dump(exclude_none=True) for event in request.events]
    try:
        return generate_team_insight(team_id, events, llm_client)
    except InvalidLLMResponse as exc:
        raise HTTPException(status_code=502, detail="invalid response from LLM provider") from exc
    except (InvalidEvent, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except LLMUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
