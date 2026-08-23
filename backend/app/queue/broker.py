import os
import random

from sqlalchemy.exc import OperationalError
from taskiq.middlewares import SmartRetryMiddleware
from taskiq_aio_pika import AioPikaBroker


class StoryGuardRetryMiddleware(SmartRetryMiddleware):
    def make_delay(self, message, retries: int) -> float:
        return (5 if retries == 1 else 30) + random.random()


broker = AioPikaBroker(os.environ["RABBITMQ_URL"]).with_middlewares(
    # Taskiq counts the initial invocation toward default_retry_count.
    StoryGuardRetryMiddleware(
        default_retry_count=3,
        types_of_exceptions=(ConnectionError, TimeoutError, OperationalError),
    )
)
