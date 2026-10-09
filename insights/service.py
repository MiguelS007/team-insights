from __future__ import annotations

import logging
import time
from typing import Any

from insights.core import LLMClient, build_prompt, calculate_metrics, parse_llm_response

logger = logging.getLogger(__name__)

LLM_TIMEOUT_SECONDS = 5.0


def generate_team_insight(team_id: str, events: list[dict[str, Any]], llm_client: LLMClient) -> dict[str, Any]:
    if not isinstance(team_id, str) or not team_id.strip():
        raise ValueError("team_id must be a non-empty string")
    if not isinstance(events, list):
        raise ValueError("events must be a list")

    metrics = calculate_metrics(events)
    prompt = build_prompt(team_id, metrics)

    started = time.perf_counter()
    raw_response = llm_client.complete(prompt, timeout_seconds=LLM_TIMEOUT_SECONDS)
    insight = parse_llm_response(raw_response)

    logger.info(
        "team insight generated",
        extra={
            "team_id": team_id,
            "event_count": len(events),
            "llm_latency_ms": round((time.perf_counter() - started) * 1000),
        },
    )

    return {"team_id": team_id, "metrics": metrics, "insight": insight}
