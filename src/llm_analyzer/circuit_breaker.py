"""
Circuit Breaker for LLM Analyzer

Implements the circuit-breaker pattern to protect Bedrock invocations from
cascading failures.

SCOPING NOTE: The module-level ``bedrock_circuit_breaker`` instance is shared
across all invocations that run within the *same Lambda execution environment*
(i.e. the same warm container).  A cold start creates a new Python process,
which resets the instance to its initial CLOSED state with failure_count=0.
This means:

* Within a warm container – state persists across invocations, providing
  genuine circuit-breaker protection.
* After a cold start – all counters are reset; ops teams can detect cold-start
  state loss by observing the "Circuit breaker cold-start reset" INFO log that
  is emitted once per container lifetime at module import time.

This is intentional and acceptable behaviour for a Lambda-hosted circuit
breaker: the circuit guards against transient Bedrock degradation events that
occur within the lifetime of a single execution environment.
"""

import logging
import time
from enum import Enum

logger = logging.getLogger(__name__)


class CircuitState(Enum):
    """Circuit breaker states."""

    CLOSED = "closed"  # Normal operation
    OPEN = "open"  # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


class CircuitBreaker:
    """
    Circuit breaker pattern for external service calls.

    Prevents cascading failures by opening the circuit after a threshold
    of consecutive failures, then testing recovery after a timeout.

    State scoping: instances are Lambda-global (module-level). State survives
    across warm invocations but is reset on cold start (new execution environment).
    """

    def __init__(self, failure_threshold: int = 5, timeout_seconds: int = 60):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of failures before opening circuit
            timeout_seconds: Seconds to wait before testing recovery
        """
        self.failure_threshold = failure_threshold
        self.timeout_seconds = timeout_seconds
        self.failure_count = 0
        self.last_failure_time: float | None = None
        self.state = CircuitState.CLOSED

    def call(self, func, *args, **kwargs):
        """
        Execute function with circuit breaker protection.

        Args:
            func: Function to execute
            *args: Positional arguments for function
            **kwargs: Keyword arguments for function

        Returns:
            Function result

        Raises:
            Exception: If circuit is open or function fails
        """
        # CIRCUIT BREAKER STATE MACHINE:
        # CLOSED -> OPEN: After failure_threshold consecutive failures
        # OPEN -> HALF_OPEN: After timeout_seconds elapsed
        # HALF_OPEN -> CLOSED: On successful call
        # HALF_OPEN -> OPEN: On failed call

        if self.state == CircuitState.OPEN:
            # Check if timeout has elapsed to test recovery
            if (
                self.last_failure_time
                and (time.time() - self.last_failure_time) > self.timeout_seconds
            ):
                # Transition to HALF_OPEN to test if service recovered
                self.state = CircuitState.HALF_OPEN
                logger.info("Circuit breaker transitioning to HALF_OPEN")
            else:
                # Circuit still open - fail fast without calling external service
                # This prevents cascading failures and gives service time to recover
                raise Exception("Circuit breaker is OPEN - rejecting request")

        try:
            # Attempt to call the function
            result = func(*args, **kwargs)
            # Success - reset failure count and close circuit
            self.on_success()
            return result
        except Exception:
            # Failure - increment counter and potentially open circuit
            self.on_failure()
            # Re-raise exception for caller to handle
            raise

    def on_success(self):
        """Handle successful call."""
        self.failure_count = 0
        if self.state == CircuitState.HALF_OPEN:
            logger.info("Circuit breaker transitioning to CLOSED")
        self.state = CircuitState.CLOSED

    def on_failure(self):
        """Handle failed call."""
        self.failure_count += 1
        self.last_failure_time = time.time()

        if self.failure_count >= self.failure_threshold:
            logger.warning(f"Circuit breaker opening after {self.failure_count} failures")
            self.state = CircuitState.OPEN


# ---------------------------------------------------------------------------
# Module-level (Lambda-global) circuit breaker instance for Bedrock calls.
#
# Cold-start log: emitted once per execution environment so that ops teams can
# correlate state resets with Lambda scaling events (new container spin-ups).
# ---------------------------------------------------------------------------
bedrock_circuit_breaker = CircuitBreaker(failure_threshold=5, timeout_seconds=60)

logger.info(
    "Circuit breaker cold-start reset: new execution environment initialised "
    "with state=CLOSED failure_count=0"
)
