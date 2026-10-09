from __future__ import annotations

import logging

import pybreaker
from limits import RateLimitItem, parse
from limits.storage import MemoryStorage
from limits.strategies import MovingWindowRateLimiter
from tenacity import (
    Retrying,
    before_sleep_log,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from tenacity.wait import wait_base

from insights.core import LLMClient

logger = logging.getLogger(__name__)

TRANSIENT_ERRORS = (TimeoutError, ConnectionError)


class LLMUnavailable(RuntimeError):
    pass


class ResilientLLMClient:
    def __init__(
        self,
        client: LLMClient,
        *,
        name: str = "llm",
        rate_limit: str = "60/minute",
        failure_threshold: int = 5,
        reset_timeout_seconds: int = 30,
        max_attempts: int = 2,
        wait: wait_base | None = None,
    ) -> None:
        self._client = client
        self._name = name
        self._rate_limit: RateLimitItem = parse(rate_limit)
        self._limiter = MovingWindowRateLimiter(MemoryStorage())
        self._breaker = pybreaker.CircuitBreaker(
            fail_max=failure_threshold,
            reset_timeout=reset_timeout_seconds,
            name=name,
        )
        self._max_attempts = max_attempts
        self._wait = wait or wait_exponential(multiplier=0.5, max=4)

    @property
    def circuit_state(self) -> str:
        return self._breaker.current_state

    def complete(self, prompt: str, timeout_seconds: float) -> str:
        retrying = Retrying(
            stop=stop_after_attempt(self._max_attempts),
            wait=self._wait,
            retry=retry_if_exception_type(TRANSIENT_ERRORS),
            before_sleep=before_sleep_log(logger, logging.WARNING),
            reraise=True,
        )
        try:
            for attempt in retrying:
                with attempt:
                    return self._call(prompt, timeout_seconds)
        except pybreaker.CircuitBreakerError as exc:
            raise LLMUnavailable(f"circuit breaker for {self._name} is open") from exc
        except TRANSIENT_ERRORS as exc:
            raise LLMUnavailable(f"{self._name} failed after {self._max_attempts} attempts") from exc

    def _call(self, prompt: str, timeout_seconds: float) -> str:
        if not self._limiter.hit(self._rate_limit, self._name):
            raise LLMUnavailable(f"rate limit exceeded for {self._name}")
        return self._breaker.call(self._client.complete, prompt, timeout_seconds)
