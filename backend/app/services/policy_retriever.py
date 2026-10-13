import hashlib
import json
import os
from functools import lru_cache
from typing import Any

import faiss
import numpy as np


DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


@lru_cache(maxsize=1)
def _load_embedding_model(model_name: str) -> Any:
    from sentence_transformers import SentenceTransformer

    return SentenceTransformer(model_name)


def _cached_retrieval(cache_key: str) -> list[dict] | None:
    redis_url = os.getenv("REDIS_URL")

    if not redis_url:
        return None

    from redis import Redis

    with Redis.from_url(redis_url, decode_responses=True) as client:
        value = client.get(cache_key)

    return json.loads(value) if value else None


def _store_retrieval(cache_key: str, results: list[dict]) -> None:
    redis_url = os.getenv("REDIS_URL")

    if not redis_url:
        return

    from redis import Redis

    ttl = int(os.getenv("REDIS_CACHE_TTL_SECONDS", "3600"))

    if ttl <= 0:
        raise RuntimeError("REDIS_CACHE_TTL_SECONDS must be positive.")

    with Redis.from_url(redis_url, decode_responses=True) as client:
        client.setex(cache_key, ttl, json.dumps(results))


def retrieve_policy_evidence(
    policy_evidence: list[dict],
    queries: dict[str, str],
    top_k: int = 3,
) -> list[dict]:
    """Retrieve source-backed policy passages relevant to each clause type."""
    passages = [
        item
        for item in policy_evidence
        if isinstance(item.get("text"), str) and item["text"].strip()
    ]

    if not passages or not queries:
        return []

    model_name = os.getenv(
        "POLICY_EMBEDDING_MODEL",
        DEFAULT_EMBEDDING_MODEL,
    )
    cache_payload = json.dumps(
        {
            "model": model_name,
            "passages": passages,
            "queries": queries,
            "top_k": top_k,
        },
        sort_keys=True,
    )
    cache_key = "policy-retrieval:" + hashlib.sha256(
        cache_payload.encode("utf-8")
    ).hexdigest()
    cached_results = _cached_retrieval(cache_key)

    if cached_results is not None:
        return cached_results

    model = _load_embedding_model(model_name)
    passage_vectors = model.encode(
        [item["text"] for item in passages],
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    passage_vectors = np.ascontiguousarray(
        passage_vectors,
        dtype=np.float32,
    )

    index = faiss.IndexFlatIP(passage_vectors.shape[1])
    index.add(passage_vectors)

    query_categories = list(queries)
    query_vectors = model.encode(
        [queries[category] for category in query_categories],
        convert_to_numpy=True,
        normalize_embeddings=True,
    )
    query_vectors = np.ascontiguousarray(
        query_vectors,
        dtype=np.float32,
    )
    scores, passage_indices = index.search(
        query_vectors,
        min(max(top_k, 1), len(passages)),
    )

    results = []

    for category, category_scores, category_indices in zip(
        query_categories,
        scores,
        passage_indices,
    ):
        for score, passage_index in zip(
            category_scores,
            category_indices,
        ):
            if passage_index < 0:
                continue

            results.append({
                **passages[int(passage_index)],
                "category": category,
                "retrieval_score": float(score),
            })

    _store_retrieval(cache_key, results)
    return results
