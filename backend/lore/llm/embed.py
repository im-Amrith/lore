"""Local embeddings with fastembed (EMBEDDING_MODEL, EMBEDDING_DIM in config).

    embed(["text", ...]) -> list[list[float]]

Each text is cached on its own (key: model + text), so re-embedding after a sync only
computes new texts. Each uncached batch counts as one "embed" call against
LLM_DAILY_CALL_CAP, counted separately from chat calls (the model runs locally, for free).
"""

from __future__ import annotations

from functools import lru_cache

from lore.config import get_settings
from lore.llm.cache import cache_get, cache_key, cache_put, count_call

BATCH = 256


@lru_cache
def _model(name: str):
    from fastembed import TextEmbedding  # heavy import (onnxruntime); load on first use

    return TextEmbedding(model_name=name)


def embed(texts: list[str]) -> list[list[float]]:
    s = get_settings()
    keys = [cache_key(s.embedding_model, "embed", t) for t in texts]
    out: list[list[float] | None] = [cache_get("embed", k) for k in keys]
    todo = [i for i, v in enumerate(out) if v is None]
    for start in range(0, len(todo), BATCH):
        idx = todo[start:start + BATCH]
        count_call("embed")
        vectors = list(_model(s.embedding_model).embed([texts[i] for i in idx]))
        for i, v in zip(idx, vectors):
            vec = [float(x) for x in v]
            if len(vec) != s.embedding_dim:
                raise ValueError(f"{s.embedding_model} returned {len(vec)} dims, EMBEDDING_DIM is {s.embedding_dim}")
            cache_put("embed", keys[i], vec)
            out[i] = vec
    return out  # type: ignore[return-value]
