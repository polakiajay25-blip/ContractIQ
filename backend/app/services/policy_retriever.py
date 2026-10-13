import hashlib
import json
import os
import re
from collections import Counter


_TOKEN_PATTERN = re.compile(r"[a-z0-9]+")

_STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "for",
    "from", "in", "is", "it", "of", "on", "or", "that", "the",
    "this", "to", "was", "were", "will", "with",
}


def _tokens(text: str) -> list[str]:
    return [
        token
        for token in _TOKEN_PATTERN.findall(text.lower())
        if token not in _STOP_WORDS
    ]


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
    """Retrieve relevant source-backed passages using token overlap."""
    passages = [
        item
        for item in policy_evidence
        if isinstance(item.get("text"), str) and item["text"].strip()
    ]

    if not passages or not queries:
        return []

    cache_payload = json.dumps(
        {
            "method": "token-overlap-v1",
            "passages": passages,
            "queries": queries,
            "top_k": top_k,
        },
        sort_keys=True,
    )
    cache_key = "policy-retrieval:" + hashlib.sha256(
        cache_payload.encode("utf-8")
    ).hexdigest()

    cached = _cached_retrieval(cache_key)
    if cached is not None:
        return cached

    passage_tokens = [
        Counter(_tokens(item["text"]))
        for item in passages
    ]
    limit = min(max(top_k, 1), len(passages))
    results = []

    for category, query in queries.items():
        query_terms = set(_tokens(query))
        if not query_terms:
            continue

        ranked = []
        for index, counts in enumerate(passage_tokens):
            overlap = query_terms.intersection(counts)
            if overlap:
                score = len(overlap) / len(query_terms)
                ranked.append((score, index))

        ranked.sort(key=lambda item: (-item[0], item[1]))

        for score, passage_index in ranked[:limit]:
            results.append({
                **passages[passage_index],
                "category": category,
                "retrieval_score": float(score),
            })

    _store_retrieval(cache_key, results)
    return results
