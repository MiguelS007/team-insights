# Team Insights

A small Python backend service that turns engineering events into **team-level productivity insights**.
It calculates deterministic metrics, sends **only aggregated metrics** to an injected LLM client, and returns a structured response ready for an API.

## Project structure

```
insights/
├── core.py         # validation, metric calculation, prompt, LLM response parsing (stdlib only)
├── service.py      # generate_team_insight: orchestrates the flow (stdlib only)
├── resilience.py   # retry, circuit breaker and rate limit around any LLM client
└── api.py          # FastAPI adapter
tests/              # 29 tests, using a fake LLM client (no network calls)
```

## Design decisions

- **Separation of concerns.** Validation, metric calculation, prompt construction and LLM response parsing are small, independent functions, each easy to test.
- **Deterministic metrics.** Metrics are calculated in plain Python, never by the LLM. The LLM only writes the summary and recommendations.
- **Privacy by design.** The prompt contains only the team ID and aggregated numbers. No PR IDs, timestamps or raw events are sent, and the prompt forbids evaluating or ranking individual engineers.
- **Dependency injection.** The service depends on an `LLMClient` protocol (`complete(prompt, timeout_seconds)`), so any provider, or a fake in tests, can be plugged in.
- **Standard library core.** `core.py` and `service.py` use only the standard library. Third-party libraries live only in the resilience and API layers.
- **Strict validation.** Malformed events raise `InvalidEvent` with a clear message. Unmatched `pr_opened` / `pr_merged` events are ignored for cycle time, as required. Invalid LLM output raises `InvalidLLMResponse`.

## Resilience

`ResilientLLMClient` wraps any LLM client and implements the same interface:

| Concern | Library | Behavior |
|---|---|---|
| Retry | `tenacity` | Retries **at most once** (2 attempts), only on transient errors (`TimeoutError`, `ConnectionError`), with exponential backoff |
| Circuit breaker | `pybreaker` | Opens after repeated failures and fails fast while the provider is down |
| Rate limit | `limits` | Moving-window limit (e.g. `60/minute`) to protect the provider quota and cost |

Invalid JSON from the LLM is **not** retried: it usually points to a prompt or model issue, and retrying would add latency and cost.

## Running

Requires Python 3.10+.

```bash
pip install -r requirements-dev.txt
pytest -v
uvicorn insights.api:app --reload
```

Example request:

```bash
curl -X POST http://localhost:8000/teams/platform/insights \
  -H "Content-Type: application/json" \
  -d '{"events": [
        {"type": "pr_opened", "id": "pr-1", "timestamp": "2026-01-01T09:00:00Z"},
        {"type": "pr_merged", "id": "pr-1", "timestamp": "2026-01-02T09:00:00Z"},
        {"type": "deployment", "timestamp": "2026-01-03T12:00:00Z"},
        {"type": "incident", "timestamp": "2026-01-04T12:00:00Z"}
      ]}'
```

API error mapping: `422` for malformed events, `502` for invalid LLM output, `503` when the LLM is unavailable (retries exhausted, circuit open or rate limited).

## Production considerations

- **FastAPI or AWS Lambda.** The service function is framework-agnostic. FastAPI runs it behind a load balancer (e.g. ECS); on Lambda, a thin handler behind API Gateway calls the same function.
- **Timeouts.** Every LLM call has a timeout, and the circuit breaker turns slowness into fast failures instead of piling up requests.
- **Idempotency.** Hash the team ID plus the event batch as an idempotency key and cache the result in Redis/ElastiCache, so the same batch is not processed or billed twice.
- **Persistence.** Raw events and metric history in Aurora/MySQL for analytical queries; generated insights in DynamoDB keyed by team and period for fast lookups.
- **Shared state.** In multi-instance deployments, rate limit counters and circuit state should move to Redis so all instances share them.
- **Observability.** Structured logs with request ID, plus metrics for latency, error rate, retries, circuit state and token usage, with alerts.
- **Quality and model versioning.** Version prompts and model names, use structured outputs when the provider supports it, and track insight quality with an evaluation set and user feedback.
- **Scale.** For large event volumes, move metric calculation to an event pipeline (SQS + Lambda workers or Glue) that stores pre-computed metrics, and call the LLM only on aggregated results.
