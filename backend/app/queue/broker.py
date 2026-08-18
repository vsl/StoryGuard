import os

from taskiq_aio_pika import AioPikaBroker

broker = AioPikaBroker(os.environ["RABBITMQ_URL"])
