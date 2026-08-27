import math
import os
from functools import lru_cache
from pathlib import Path

import yaml


DEFAULT_CONFIG = Path(__file__).parents[3] / "config" / "models.yaml"


def local_model_config(kind: str) -> dict[str, object]:
    path = Path(os.environ.get("STORYGUARD_MODELS_CONFIG", DEFAULT_CONFIG))
    return yaml.safe_load(path.read_text())["models"][kind]["local_default"]


MODEL_CONFIG = local_model_config("embeddings")
EMBEDDING_REPOSITORY = str(MODEL_CONFIG["hf_repository"])
EMBEDDING_REVISION = str(MODEL_CONFIG["revision"])
EMBEDDING_VERSION = str(MODEL_CONFIG["version"])
EMBEDDING_DIMENSION = int(MODEL_CONFIG["dimension"])


class LocalEmbeddingProvider:
    def __init__(self, model=None) -> None:
        if model is None:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(
                EMBEDDING_REPOSITORY,
                revision=EMBEDDING_REVISION,
            )
        self.model = model

    def _validated(self, vectors) -> list[list[float]]:
        rows = vectors.tolist() if hasattr(vectors, "tolist") else vectors
        if rows and isinstance(rows[0], (int, float)):
            rows = [rows]
        result = [[float(value) for value in row] for row in rows]
        if any(
            len(row) != EMBEDDING_DIMENSION
            or not all(math.isfinite(value) for value in row)
            for row in result
        ):
            raise ValueError(
                f"Embedding model must return finite {EMBEDDING_DIMENSION}-dimensional vectors"
            )
        return result

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        return self._validated(
            self.model.encode_document(
                texts,
                batch_size=8,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        )

    def embed_query(self, text: str) -> list[float]:
        return self._validated(
            self.model.encode_query(
                text,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
        )[0]


@lru_cache(maxsize=1)
def get_embedding_provider() -> LocalEmbeddingProvider:
    return LocalEmbeddingProvider()


def embed_documents(texts: list[str]) -> list[list[float]]:
    return get_embedding_provider().embed_documents(texts)


def embed_query(text: str) -> list[float]:
    return get_embedding_provider().embed_query(text)
