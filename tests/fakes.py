VALID_RESPONSE = '{"summary": "Healthy delivery flow.", "recommendations": ["Monitor cycle time."]}'

EVENTS = [
    {"type": "pr_opened", "id": "pr-1", "timestamp": "2026-01-01T09:00:00Z"},
    {"type": "pr_merged", "id": "pr-1", "timestamp": "2026-01-02T09:00:00Z"},
    {"type": "deployment", "timestamp": "2026-01-03T12:00:00Z"},
    {"type": "incident", "timestamp": "2026-01-04T12:00:00Z"},
]


class FakeLLMClient:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.prompts = []

    def complete(self, prompt, timeout_seconds):
        self.prompts.append(prompt)
        response = self.responses.pop(0) if len(self.responses) > 1 else self.responses[0]
        if isinstance(response, Exception):
            raise response
        return response
