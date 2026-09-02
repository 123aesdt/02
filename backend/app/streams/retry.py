from dataclasses import dataclass


@dataclass(frozen=True)
class RetryPolicy:
    max_delivery_attempts: int
    base_delay_ms: int
    max_delay_ms: int

    def should_retry(self, delivery_count: int) -> bool:
        return delivery_count < self.max_delivery_attempts

    def backoff_ms(self, delivery_count: int) -> int:
        return min(self.base_delay_ms * (2 ** (delivery_count - 1)), self.max_delay_ms)
