from __future__ import annotations

import sys
import tempfile
from collections.abc import Callable
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
    query: str,
    *,
    db_path: Path,
    id_for_path: Callable[[Path], str | None],
    limit: int,
) -> list[str]:
    from bookmark_tools.search_index import search_index

    results = search_index(query, database_path=db_path, limit=limit)
    return [rid for r in results if (rid := id_for_path(r.path))]


def _ranked_ids_semantic(
    query: str,
    *,
    db_path: Path,
    id_for_path: Callable[[Path], str | None],
    limit: int,
    config: dict[str, str] | None = None,
) -> list[str]:
    from bookmark_tools.embeddings import semantic_search

    matches = semantic_search(
        query, database_path=db_path, limit=limit, threshold=0.0, config=config
    )
    return [rid for m in matches if (rid := id_for_path(m.path))]


def _ranked_ids_hybrid(
    query: str,
    *,
    db_path: Path,
    id_for_path: Callable[[Path], str | None],
    limit: int,
    config: dict[str, str] | None = None,
) -> list[str]:
    from bookmark_tools.embeddings import semantic_search
    from bookmark_tools.search import (
        _embedding_match_to_result,
        _reciprocal_rank_fusion,
    )
    from bookmark_tools.search_index import search_index

    bm25_r = search_index(query, database_path=db_path, limit=limit * 3)
    sem_m = semantic_search(
        query, database_path=db_path, limit=limit * 3, threshold=0.0, config=config
    )
    sem_r = [_embedding_match_to_result(m) for m in sem_m]
    fused = _reciprocal_rank_fusion(bm25_r, sem_r, limit)
    return [rid for r in fused if (rid := id_for_path(r.path))]


def _score_queries(
    queries: list[dict],
    *,
    db_path: Path,
    id_for_path: Callable[[Path], str | None],
    modes: list[str],
    k_values: list[int],
    limit: int,
    config: dict[str, str] | None = None,
) -> dict[str, dict[str, float]]:
    """Run all modes against a query list; return metrics_by_mode."""
    from evals.metrics import aggregate_metrics, score_query

    metrics_by_mode: dict[str, dict[str, float]] = {}
    for mode in modes:
        print(f"Evaluating {mode!r} on {len(queries)} queries ...")
        per_query: list[dict[str, float]] = []
        for q in queries:
            try:
                if mode == "bm25":
                    ranked = _ranked_ids_bm25(
                        q["text"], db_path=db_path, id_for_path=id_for_path, limit=limit
                    )
                elif mode == "semantic":
                    ranked = _ranked_ids_semantic(
                        q["text"],
                        db_path=db_path,
                        id_for_path=id_for_path,
                        limit=limit,
                        config=config,
                    )
                else:
                    ranked = _ranked_ids_hybrid(
                        q["text"],
                        db_path=db_path,
                        id_for_path=id_for_path,
                        limit=limit,
                        config=config,
                    )
            except ValueError:
                ranked = []
            per_query.append(score_query(ranked, q["relevant"], k_values))
        metrics_by_mode[mode] = aggregate_metrics(per_query, k_values)
    return metrics_by_mode


def _filter_modes(modes: list[str]) -> list[str]:
    """Drop semantic/hybrid when no API key is configured."""
    api_available = _has_api_key()
    effective: list[str] = []
    for mode in modes:
        if mode in ("semantic", "hybrid") and not api_available:
            print(f"  skipping {mode!r} — no API key configured")
        else:
            effective.append(mode)
    return effective


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
    if dataset == "personal":
        return _run_personal(
            modes=modes, k_values=k_values, limit=limit, query_limit=query_limit
        )
    print(
        f"Unknown dataset: {dataset!r}. Use beir:<name> or personal.", file=sys.stderr
    )
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
    from evals.reporter import _git_info, print_metrics_table, write_snapshot
    from evals.vault_builder import build_vault_from_docs

    print(f"Loading BEIR/{dataset_name} ...")
    corpus, queries, qrels = load_beir_dataset(dataset_name, query_limit=query_limit)
    print(f"  {len(corpus)} docs | {len(queries)} queries | {len(qrels)} qrel sets")

    effective_modes = _filter_modes(modes)
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

        def id_for_path(path: Path) -> str | None:
            return stem_to_id.get(path.stem)

        print("Building BM25 index ...")
        docs = collect_search_documents(bookmarks_dir=vault_dir)
        _build_bm25_index(docs, db_path)

        if any(m in ("semantic", "hybrid") for m in effective_modes):
            print("Building embeddings (API calls required) ...")
            _build_embeddings(docs, db_path)

        # Normalise to shared query format {text, relevant}
        normalised = [
            {"text": q["text"], "relevant": qrels.get(q["query_id"], set())}
            for q in queries
        ]
        metrics_by_mode = _score_queries(
            normalised,
            db_path=db_path,
            id_for_path=id_for_path,
            modes=effective_modes,
            k_values=k_values,
            limit=limit,
        )

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


def _run_personal(
    *,
    modes: list[str],
    k_values: list[int],
    limit: int,
    query_limit: int | None,
) -> int:
    from bookmark_tools.paths import (
        get_search_index_path,
        load_env,
        require_bookmarks_dir,
    )
    from bookmark_tools.search_documents import collect_search_documents
    from bookmark_tools.search_index import update_search_index

    from evals.datasets.personal.schema import validate
    from evals.reporter import _git_info, print_metrics_table, write_snapshot

    queries_path = (
        Path(__file__).parent.parent / "datasets" / "personal" / "queries.yaml"
    )

    load_env()
    bookmarks_dir = require_bookmarks_dir()
    db_path = get_search_index_path()

    print("Validating personal queries against vault ...")
    try:
        personal_queries, vault_id_map = validate(queries_path, bookmarks_dir)
    except ValueError as exc:
        print(f"  Error: {exc}", file=sys.stderr)
        return 1

    if not personal_queries:
        print(
            f"  No queries in {queries_path}.\n"
            "  Add entries following the format documented at the top of that file."
        )
        return 0

    if query_limit is not None:
        personal_queries = personal_queries[:query_limit]

    print(f"  {len(personal_queries)} queries | {len(vault_id_map)} notes in vault")

    effective_modes = _filter_modes(modes)
    if not effective_modes:
        print("No runnable modes.", file=sys.stderr)
        return 1

    # Build {str(path) → note_id} for result lookup
    path_to_id: dict[str, str] = {
        str(path): note_id for note_id, path in vault_id_map.items()
    }

    def id_for_path(path: Path) -> str | None:
        return path_to_id.get(str(path))

    print("Refreshing search index (incremental) ...")
    docs = collect_search_documents(bookmarks_dir=bookmarks_dir)
    update_search_index(docs, database_path=db_path)

    if any(m in ("semantic", "hybrid") for m in effective_modes):
        from bookmark_tools.embeddings import refresh_embeddings

        print("Refreshing embeddings (incremental) ...")
        refresh_embeddings(docs, database_path=db_path)

    # Normalise to shared format
    normalised = [
        {"text": q.query, "relevant": q.relevant_ids} for q in personal_queries
    ]
    metrics_by_mode = _score_queries(
        normalised,
        db_path=db_path,
        id_for_path=id_for_path,
        modes=effective_modes,
        k_values=k_values,
        limit=limit,
    )

    print()
    print_metrics_table(metrics_by_mode, k_values)

    payload: dict[str, object] = {
        "suite": "search",
        "dataset": "personal",
        "git": _git_info(),
        "n_notes": len(vault_id_map),
        "n_queries": len(personal_queries),
        "k_values": k_values,
        "metrics_by_mode": metrics_by_mode,
    }
    snap = write_snapshot("search-personal", payload)
    print(f"\nSnapshot: {snap}")
    return 0
