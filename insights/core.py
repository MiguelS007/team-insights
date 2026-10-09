from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Protocol

EVENT_TYPES = {"pr_opened", "pr_merged", "deployment", "incident"}
PR_EVENT_TYPES = {"pr_opened", "pr_merged"}


class LLMClient(Protocol):
    def complete(self, prompt: str, timeout_seconds: float) -> str: ...


class InvalidEvent(ValueError):
    pass


class InvalidLLMResponse(ValueError):
    pass


def parse_timestamp(value: Any) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise InvalidEvent(f"timestamp must be an ISO-8601 string ending in Z: {value!r}")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise InvalidEvent(f"invalid timestamp: {value!r}") from exc
    return parsed.astimezone(timezone.utc)


def validate_event(event: Any) -> tuple[str, str | None, datetime]:
    if not isinstance(event, dict):
        raise InvalidEvent("each event must be an object")

    event_type = event.get("type")
    if event_type not in EVENT_TYPES:
        raise InvalidEvent(f"unsupported event type: {event_type!r}")

    event_id = event.get("id")
    if event_type in PR_EVENT_TYPES and (not isinstance(event_id, str) or not event_id):
        raise InvalidEvent(f"{event_type} requires a non-empty string id")
    if event_id is not None and not isinstance(event_id, str):
        raise InvalidEvent("id must be a string when provided")

    return event_type, event_id, parse_timestamp(event.get("timestamp"))


def calculate_metrics(events: list[dict[str, Any]]) -> dict[str, int | float | None]:
    opened: dict[str, datetime] = {}
    merged: dict[str, datetime] = {}
    deployments = 0
    incidents = 0

    for event in events:
        event_type, event_id, timestamp = validate_event(event)
        if event_type == "pr_opened":
            opened[event_id] = timestamp
        elif event_type == "pr_merged":
            merged[event_id] = timestamp
        elif event_type == "deployment":
            deployments += 1
        else:
            incidents += 1

    cycle_times = [
        (merged_at - opened[pr_id]).total_seconds() / 3600
        for pr_id, merged_at in merged.items()
        if pr_id in opened and merged_at >= opened[pr_id]
    ]
    average = round(sum(cycle_times) / len(cycle_times), 2) if cycle_times else None

    return {
        "merged_prs": len(merged),
        "average_pr_cycle_time_hours": average,
        "deployments": deployments,
        "incidents": incidents,
    }


def build_prompt(team_id: str, metrics: dict[str, int | float | None]) -> str:
    return (
        "You generate team-level engineering productivity insights. "
        "Never evaluate, rank, or compare individual engineers, and do not invent data. "
        "Use only the aggregated metrics below. "
        'Respond with JSON only, in this shape: {"summary": string, "recommendations": [string]}.\n\n'
        f"Team: {team_id}\n"
        f"Aggregated metrics: {json.dumps(metrics, sort_keys=True)}"
    )


def parse_llm_response(raw: str) -> dict[str, Any]:
    try:
        data = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise InvalidLLMResponse("LLM response is not valid JSON") from exc

    if not isinstance(data, dict):
        raise InvalidLLMResponse("LLM response must be a JSON object")

    summary = data.get("summary")
    recommendations = data.get("recommendations")

    if not isinstance(summary, str) or not summary.strip():
        raise InvalidLLMResponse("summary must be a non-empty string")
    if not isinstance(recommendations, list) or not all(isinstance(item, str) for item in recommendations):
        raise InvalidLLMResponse("recommendations must be a list of strings")

    return {"summary": summary, "recommendations": recommendations}
