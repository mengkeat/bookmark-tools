from __future__ import annotations

import math


def precision_at_k(ranked_ids: list[str], relevant: set[str], k: int) -> float:
    """P@k: fraction of top-k results that are relevant."""
    if k == 0:
        return 0.0
    return sum(1 for doc_id in ranked_ids[:k] if doc_id in relevant) / k


def recall_at_k(ranked_ids: list[str], relevant: set[str], k: int) -> float:
    """Recall@k: fraction of relevant docs found in top-k."""
    if not relevant:
        return 0.0
    return sum(1 for doc_id in ranked_ids[:k] if doc_id in relevant) / len(relevant)


def reciprocal_rank(ranked_ids: list[str], relevant: set[str]) -> float:
    """MRR contribution for one query: 1/rank of first relevant result."""
    for rank, doc_id in enumerate(ranked_ids, start=1):
        if doc_id in relevant:
            return 1.0 / rank
    return 0.0


def ndcg_at_k(ranked_ids: list[str], relevant: set[str], k: int) -> float:
    """nDCG@k with binary relevance."""
    if not relevant:
        return 0.0
    dcg = sum(
        1.0 / math.log2(rank + 1)
        for rank, doc_id in enumerate(ranked_ids[:k], start=1)
        if doc_id in relevant
    )
    ideal_len = min(len(relevant), k)
    ideal_dcg = sum(1.0 / math.log2(i + 2) for i in range(ideal_len))
    return dcg / ideal_dcg if ideal_dcg else 0.0


def score_query(
    ranked_ids: list[str],
    relevant: set[str],
    k_values: list[int],
) -> dict[str, float]:
    """Compute all metrics for a single query at multiple k values."""
    result: dict[str, float] = {"mrr": reciprocal_rank(ranked_ids, relevant)}
    for k in k_values:
        result[f"p@{k}"] = precision_at_k(ranked_ids, relevant, k)
        result[f"recall@{k}"] = recall_at_k(ranked_ids, relevant, k)
        result[f"ndcg@{k}"] = ndcg_at_k(ranked_ids, relevant, k)
    return result


def aggregate_metrics(
    query_metrics: list[dict[str, float]],
    k_values: list[int],
) -> dict[str, float]:
    """Macro-average per-query scores across all queries."""
    if not query_metrics:
        return {}
    n = len(query_metrics)
    result: dict[str, float] = {"mrr": sum(m["mrr"] for m in query_metrics) / n}
    for k in k_values:
        result[f"p@{k}"] = sum(m[f"p@{k}"] for m in query_metrics) / n
        result[f"recall@{k}"] = sum(m[f"recall@{k}"] for m in query_metrics) / n
        result[f"ndcg@{k}"] = sum(m[f"ndcg@{k}"] for m in query_metrics) / n
    return result
