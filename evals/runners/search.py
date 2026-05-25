from __future__ import annotations

import sys
import tempfile
from pathlib import Path


def _has_api_key() -> bool:
    from bookmark_tools.config import load_config

    return load_config().has_api_key


def _build_bm25_index(docs: list, db_path: Path) -> None:
    from bookmark_tools.search_index import rebuild_search_index

    rebuild_search_index(docs, database_path=db_path)


def _build_embeddings(docs: list, db_path: Path) -> None:
    from bookmark_tools.embeddings import refresh_embeddings

    refresh_embeddings(docs, database_path=db_path)


def _ranked_ids_bm25(
    query: str, *, db_path: Path, stem_to_id: dict[str, str], limit: int
) -> list[str]:
    from bookmark_tools.search_index import search_index

    results = search_index(query, database_path=db_path, limit=limit)
    return [stem_to_id[r.path.stem] for r in results if r.path.stem in stem_to_id]


def _ranked_ids_semantic(
    query: str, *, db_path: Path, stem_to_id: dict[str, str], limit: int
) -> list[str]:
    from bookmark_tools.embeddings import semantic_search

    matches = semantic_search(query, database_path=db_path, limit=limit, threshold=0.0)
    return [stem_to_id[m.path.stem] for m in matches if m.path.stem in stem_to_id]


def _ranked_ids_hybrid(
    query: str, *, db_path: Path, stem_to_id: dict[str, str], limit: int
) -> list[str]:
    from bookmark_tools.embeddings import semantic_search
    from bookmark_tools.search import _embedding_match_to_result, _reciprocal_rank_fusion
    from bookmark_tools.search_index import search_index

    bm25_r = search_index(query, database_path=db_path, limit=limit * 3)
    sem_m = semantic_search(query, database_path=db_path, limit=limit * 3, threshold=0.0)
    sem_r = [_embedding_match_to_result(m) for m in sem_m]
    fused = _reciprocal_rank_fusion(bm25_r, sem_r, limit)
    return [stem_to_id[r.path.stem] for r in fused if r.path.stem in stem_to_id]


def run_search(
    *,
    dataset: str = "beir:nfcorpus",
    modes: list[str],
    k_values: list[int],
    limit: int = 100,
    query_limit: int | None = None,
) -> int:
    if dataset.startswith("beir:"):
        return _run_beir(
            dataset_name=dataset.removeprefix("beir:"),
            modes=modes,
            k_values=k_values,
            limit=limit,
            query_limit=query_limit,
        )
    print(f"Unknown dataset: {dataset!r}", file=sys.stderr)
    return 1


def _run_beir(
    *,
    dataset_name: str,
    modes: list[str],
    k_values: list[int],
    limit: int,
    query_limit: int | None,
) -> int:
    from bookmark_tools.search_documents import collect_search_documents

    from evals.datasets.beir.adapter import load_beir_dataset
    from evals.metrics import aggregate_metrics, score_query
    from evals.reporter import _git_info, print_metrics_table, write_snapshot
    from evals.vault_builder import build_vault_from_docs

    print(f"Loading BEIR/{dataset_name} ...")
    corpus, queries, qrels = load_beir_dataset(dataset_name, query_limit=query_limit)
    print(f"  {len(corpus)} docs | {len(queries)} queries | {len(qrels)} qrel sets")

    # Drop modes that require an API key when none is configured
    api_available = _has_api_key()
    effective_modes: list[str] = []
    for mode in modes:
        if mode in ("semantic", "hybrid") and not api_available:
            print(f"  skipping {mode!r} — no API key configured")
        else:
            effective_modes.append(mode)
    if not effective_modes:
        print("No runnable modes.", file=sys.stderr)
        return 1

    with tempfile.TemporaryDirectory(prefix="bookmark-eval-") as tmpdir:
        vault_dir = Path(tmpdir) / "vault"
        db_path = Path(tmpdir) / "search.sqlite3"

        print(f"Writing {len(corpus)} notes to temp vault ...")
        doc_id_to_stem = build_vault_from_docs(
            vault_dir, corpus, url_prefix=f"urn:beir:{dataset_name}"
        )
        stem_to_id = {stem: doc_id for doc_id, stem in doc_id_to_stem.items()}

        print("Building BM25 index ...")
        docs = collect_search_documents(bookmarks_dir=vault_dir)
        _build_bm25_index(docs, db_path)

        if any(m in ("semantic", "hybrid") for m in effective_modes):
            print("Building embeddings (API calls required) ...")
            _build_embeddings(docs, db_path)

        metrics_by_mode: dict[str, dict[str, float]] = {}
        for mode in effective_modes:
            print(f"Evaluating {mode!r} on {len(queries)} queries ...")
            per_query: list[dict[str, float]] = []
            for q in queries:
                try:
                    if mode == "bm25":
                        ranked = _ranked_ids_bm25(
                            q["text"], db_path=db_path, stem_to_id=stem_to_id, limit=limit
                        )
                    elif mode == "semantic":
                        ranked = _ranked_ids_semantic(
                            q["text"], db_path=db_path, stem_to_id=stem_to_id, limit=limit
                        )
                    else:
                        ranked = _ranked_ids_hybrid(
                            q["text"], db_path=db_path, stem_to_id=stem_to_id, limit=limit
                        )
                except ValueError:
                    # No searchable terms in this query
                    ranked = []

                per_query.append(
                    score_query(ranked, qrels.get(q["query_id"], set()), k_values)
                )

            metrics_by_mode[mode] = aggregate_metrics(per_query, k_values)

    print()
    print_metrics_table(metrics_by_mode, k_values)

    payload: dict[str, object] = {
        "suite": "search",
        "dataset": f"beir:{dataset_name}",
        "git": _git_info(),
        "n_corpus": len(corpus),
        "n_queries": len(queries),
        "k_values": k_values,
        "metrics_by_mode": metrics_by_mode,
    }
    snap = write_snapshot(f"search-beir-{dataset_name}", payload)
    print(f"\nSnapshot: {snap}")
    return 0
