import math
from dataclasses import replace
from functools import lru_cache
from typing import TYPE_CHECKING, Protocol

from app.ai.embeddings import local_model_config


if TYPE_CHECKING:
    from app.ai.retrieval import RetrievedChunk


MODEL_CONFIG = local_model_config("rerankers")
RERANKER_REPOSITORY = str(MODEL_CONFIG["hf_repository"])
RERANKER_REVISION = str(MODEL_CONFIG["revision"])
RERANKER_VERSION = str(MODEL_CONFIG["version"])
RERANKER_BATCH_SIZE = 30


class Reranker(Protocol):
    def rerank(
        self, query: str, candidates: list["RetrievedChunk"], top_k: int
    ) -> list["RetrievedChunk"]: ...


class LocalCrossEncoderReranker:
    def __init__(self, model=None) -> None:
        if model is None:
            import torch
            from sentence_transformers import CrossEncoder

            model = CrossEncoder(
                RERANKER_REPOSITORY,
                revision=RERANKER_REVISION,
                activation_fn=torch.nn.Identity(),
            )
        self.model = model

    def rerank(
        self, query: str, candidates: list["RetrievedChunk"], top_k: int
    ) -> list["RetrievedChunk"]:
        query = query.strip()
        if not query:
            raise ValueError("Reranking query must not be empty")
        if not 1 <= top_k <= 100:
            raise ValueError("top_k must be between 1 and 100")
        if not candidates:
            return []

        scores = self.model.predict(
            [(query, candidate.text) for candidate in candidates],
            batch_size=RERANKER_BATCH_SIZE,
            show_progress_bar=False,
        )
        scores = scores.tolist() if hasattr(scores, "tolist") else list(scores)
        scores = [float(score) for score in scores]
        if len(scores) != len(candidates) or not all(map(math.isfinite, scores)):
            raise ValueError("Reranker must return one finite score per candidate")

        ranked = sorted(
            zip(candidates, scores, strict=True),
            key=lambda item: (-item[1], item[0].chunk_id),
        )
        return [replace(candidate, score=score) for candidate, score in ranked[:top_k]]


@lru_cache(maxsize=1)
def get_reranker() -> Reranker:
    return LocalCrossEncoderReranker()


def rerank(
    query: str, candidates: list["RetrievedChunk"], top_k: int
) -> list["RetrievedChunk"]:
    return get_reranker().rerank(query, candidates, top_k)
