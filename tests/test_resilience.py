import pytest
from tenacity import wait_none

from insights.resilience import LLMUnavailable, ResilientLLMClient
from tests.fakes import VALID_RESPONSE, FakeLLMClient


def make_client(fake, **kwargs):
    return ResilientLLMClient(fake, wait=wait_none(), **kwargs)


def test_retries_once_after_transient_failure():
    fake = FakeLLMClient(TimeoutError(), VALID_RESPONSE)
    assert make_client(fake).complete("prompt", 5) == VALID_RESPONSE
    assert len(fake.prompts) == 2


def test_gives_up_after_one_retry():
    fake = FakeLLMClient(TimeoutError())
    with pytest.raises(LLMUnavailable):
        make_client(fake).complete("prompt", 5)
    assert len(fake.prompts) == 2


def test_does_not_retry_non_transient_errors():
    fake = FakeLLMClient(KeyError("bug"))
    with pytest.raises(KeyError):
        make_client(fake).complete("prompt", 5)
    assert len(fake.prompts) == 1


def test_circuit_opens_after_repeated_failures():
    fake = FakeLLMClient(ConnectionError())
    client = make_client(fake, failure_threshold=2, max_attempts=1)

    with pytest.raises(LLMUnavailable):
        client.complete("prompt", 5)
    with pytest.raises(LLMUnavailable):
        client.complete("prompt", 5)

    calls_before = len(fake.prompts)
    with pytest.raises(LLMUnavailable, match="circuit breaker"):
        client.complete("prompt", 5)
    assert len(fake.prompts) == calls_before
    assert client.circuit_state == "open"


def test_rate_limit_blocks_extra_calls():
    fake = FakeLLMClient(VALID_RESPONSE)
    client = make_client(fake, rate_limit="2/minute")

    client.complete("prompt", 5)
    client.complete("prompt", 5)
    with pytest.raises(LLMUnavailable, match="rate limit"):
        client.complete("prompt", 5)
    assert len(fake.prompts) == 2
