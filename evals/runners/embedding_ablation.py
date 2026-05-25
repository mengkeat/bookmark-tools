from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path
from typing import Callable

ABLATION_CACHE_DIR = Path.home() / ".cache" / "bookmark-tools" / "evals" / "ablation"


def _get_combo_config(model: str, dimensions: int) -> dict[str, str] | None:
    from bookmark_tools.config import load_config

    cfg = load_config(overrides={"embedding_model": model, "embedding_dimensions": str(dimensions)})
    return cfg.as_llm_dict()


def _print_ablation_table(
    results: list[dict],
    k_values: list[int],
    modes: list[str],
) -> None:
    metric_keys = (
        [f"p@{k}" for k in k_values]
        + [f"recall@{k}" for k in k_values]
        + ["mrr"]
        + [f"ndcg@{k}" for k in k_values]
    )
    model_col = max(len(r["model"]) for r in results) + 2
    dims_col = 6
    val_col = 10
    baseline = results[0]

    for mode in modes:
        print(f"\n[mode: {mode}]")
        header = (
            "model".ljust(model_col)
            + "dims".ljust(dims_col)
            + "  "
            + "  ".join(k.ljust(val_col) for k in metric_keys)
        )
        print(header)
        print("-" * len(header))
        for i, r in enumerate(results):
            m = r["metrics_by_mode"].get(mode, {})
            tag = "  (baseline)" if i == 0 else ""
            if i == 0:
                vals = "  ".join(f"{m.get(k, 0.0):.4f}".ljust(val_col) for k in metric_keys)
            else:
                bm = baseline["metrics_by_mode"].get(mode, {})
                vals = "  ".join(
                    f"{'+'if (d:=m.get(k,0.0)-bm.get(k,0.0))>=0 else ''}{d:.4f}".ljust(val_col)
                    for k in metric_keys
                )
            print(r["model"].ljust(model_col) + str(r["dimensions"]).ljust(dims_col) + "  " + vals + tag)


def run_ablation(
    *,
    dataset: str = "beir:nfcorpus",
    models: list[str],
    dimensions: list[int],
    modes: list[str],
    k_values: list[int],
    limit: int = 100,
    query_limit: int | None = None,
) -> int:
    combos = [(m, d) for m in models for d in dimensions]
    if not combos:
        print("No model/dimension combos specified.", file=sys.stderr)
        return 1

    if dataset.startswith("beir:"):
        return _run_beir_ablation(
            dataset_name=dataset.removeprefix("beir:"),
            combos=combos,
            modes=modes,
            k_values=k_values,
            limit=limit,
            query_limit=query_limit,
        )
    if dataset == "personal":
        return _run_personal_ablation(
            combos=combos,
            modes=modes,
            k_values=k_values,
            limit=limit,
            query_limit=query_limit,
        )
    print(f"Unknown dataset: {dataset!r}. Use beir:<name> or personal.", file=sys.stderr)
    return 1


def _run_beir_ablation(
    *,
    dataset_name: str,
    combos: list[tuple[str, int]],
    modes: list[str],
    k_values: list[int],
    limit: int,
    query_limit: int | None,
) -> int:
    from bookmark_tools.search_documents import collect_search_documents

    from evals.datasets.beir.adapter import load_beir_dataset
    from evals.reporter import _git_info, write_snapshot
    from evals.runners.search import _build_bm25_index, _filter_modes, _score_queries
    from evals.vault_builder import build_vault_from_docs

    print(f"Loading BEIR/{dataset_name} ...")
    corpus, queries, qrels = load_beir_dataset(dataset_name, query_limit=query_limit)
    print(f"  {len(corpus)} docs | {len(queries)} queries | {len(qrels)} qrel sets")

    effective_modes = _filter_modes(modes)
    if not effective_modes:
        print("No runnable modes.", file=sys.stderr)
        return 1

    embedding_modes = [m for m in effective_modes if m in ("semantic", "hybrid")]
    normalised = [
        {"text": q["text"], "relevant": qrels.get(q["query_id"], set())}
        for q in queries
    ]

    with tempfile.TemporaryDirectory(prefix="bookmark-eval-ablation-") as tmpdir:
        vault_dir = Path(tmpdir) / "vault"
        base_db = Path(tmpdir) / "base.sqlite3"

        print(f"Writing {len(corpus)} notes to temp vault ...")
        doc_id_to_stem = build_vault_from_docs(vault_dir, corpus, url_prefix=f"urn:beir:{dataset_name}")
        stem_to_id = {stem: doc_id for doc_id, stem in doc_id_to_stem.items()}
        id_for_path: Callable[[Path], str | None] = lambda p: stem_to_id.get(p.stem)

        print("Building BM25 index ...")
        docs = collect_search_documents(bookmarks_dir=vault_dir)
        _build_bm25_index(docs, base_db)

        # BM25 doesn't depend on the embedding combo — score it once.
        bm25_metrics: dict[str, float] | None = None
        if "bm25" in effective_modes:
            bm25_result = _score_queries(
                normalised,
                db_path=base_db,
                id_for_path=id_for_path,
                modes=["bm25"],
                k_values=k_values,
                limit=limit,
            )
            bm25_metrics = bm25_result["bm25"]

        results: list[dict] = []
        for model, dims in combos:
            print(f"\n--- Combo: {model} / {dims}d ---")
            combo_config = _get_combo_config(model, dims)
            if combo_config is None and embedding_modes:
                print("  Skipping embedding modes — no API key configured.")
                combo_em_modes: list[str] = []
            else:
                combo_em_modes = embedding_modes

            combo_db = Path(tmpdir) / f"combo_{model.replace('/', '_').replace('-', '_')}_{dims}.sqlite3"
            shutil.copy2(base_db, combo_db)

            if combo_em_modes and combo_config:
                from bookmark_tools.embeddings import refresh_embeddings

                print(f"  Building embeddings ({model}, {dims}d) ...")
                refresh_embeddings(docs, database_path=combo_db, config=combo_config)

            combo_metrics: dict[str, dict[str, float]] = {}
            if bm25_metrics is not None:
                combo_metrics["bm25"] = bm25_metrics

            if combo_em_modes:
                sem_result = _score_queries(
                    normalised,
                    db_path=combo_db,
                    id_for_path=id_for_path,
                    modes=combo_em_modes,
                    k_values=k_values,
                    limit=limit,
                    config=combo_config,
                )
                combo_metrics.update(sem_result)

            results.append({"model": model, "dimensions": dims, "metrics_by_mode": combo_metrics})

    print()
    _print_ablation_table(results, k_values, effective_modes)

    payload: dict[str, object] = {
        "suite": "ablation",
        "dataset": f"beir:{dataset_name}",
        "git": _git_info(),
        "combos": [{"model": m, "dimensions": d} for m, d in combos],
        "modes": effective_modes,
        "k_values": k_values,
        "n_corpus": len(corpus),
        "n_queries": len(queries),
        "results": results,
    }
    snap = write_snapshot(f"ablation-beir-{dataset_name}", payload)
    print(f"\nSnapshot: {snap}")
    return 0


def _run_personal_ablation(
    *,
    combos: list[tuple[str, int]],
    modes: list[str],
    k_values: list[int],
    limit: int,
    query_limit: int | None,
) -> int:
    from bookmark_tools.paths import get_search_index_path, load_env, require_bookmarks_dir
    from bookmark_tools.search_documents import collect_search_documents
    from bookmark_tools.search_index import update_search_index

    from evals.datasets.personal.schema import validate
    from evals.reporter import _git_info, write_snapshot
    from evals.runners.search import _filter_modes, _score_queries

    queries_path = Path(__file__).parent.parent / "datasets" / "personal" / "queries.yaml"

    load_env()
    bookmarks_dir = require_bookmarks_dir()
    bm25_db = get_search_index_path()

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

    embedding_modes = [m for m in effective_modes if m in ("semantic", "hybrid")]
    path_to_id: dict[str, str] = {str(path): note_id for note_id, path in vault_id_map.items()}
    id_for_path: Callable[[Path], str | None] = lambda p: path_to_id.get(str(p))

    print("Refreshing BM25 index (incremental) ...")
    docs = collect_search_documents(bookmarks_dir=bookmarks_dir)
    update_search_index(docs, database_path=bm25_db)

    normalised = [{"text": q.query, "relevant": q.relevant_ids} for q in personal_queries]

    # BM25 scored once against the real index.
    bm25_metrics: dict[str, float] | None = None
    if "bm25" in effective_modes:
        bm25_result = _score_queries(
            normalised,
            db_path=bm25_db,
            id_for_path=id_for_path,
            modes=["bm25"],
            k_values=k_values,
            limit=limit,
        )
        bm25_metrics = bm25_result["bm25"]

    ABLATION_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    for model, dims in combos:
        print(f"\n--- Combo: {model} / {dims}d ---")
        combo_config = _get_combo_config(model, dims)
        if combo_config is None and embedding_modes:
            print("  Skipping embedding modes — no API key configured.")
            combo_em_modes: list[str] = []
        else:
            combo_em_modes = embedding_modes

        safe_model = model.replace("/", "_").replace("-", "_")
        combo_db = ABLATION_CACHE_DIR / f"personal_{safe_model}_{dims}.sqlite3"

        # Seed from real BM25 DB so FTS5 tables are available for hybrid.
        shutil.copy2(bm25_db, combo_db)

        if combo_em_modes and combo_config:
            from bookmark_tools.embeddings import refresh_embeddings

            print(f"  Building embeddings ({model}, {dims}d) ...")
            refresh_embeddings(docs, database_path=combo_db, config=combo_config)

        combo_metrics: dict[str, dict[str, float]] = {}
        if bm25_metrics is not None:
            combo_metrics["bm25"] = bm25_metrics

        if combo_em_modes:
            sem_result = _score_queries(
                normalised,
                db_path=combo_db,
                id_for_path=id_for_path,
                modes=combo_em_modes,
                k_values=k_values,
                limit=limit,
                config=combo_config,
            )
            combo_metrics.update(sem_result)

        results.append({"model": model, "dimensions": dims, "metrics_by_mode": combo_metrics})

    print()
    _print_ablation_table(results, k_values, effective_modes)

    payload: dict[str, object] = {
        "suite": "ablation",
        "dataset": "personal",
        "git": _git_info(),
        "combos": [{"model": m, "dimensions": d} for m, d in combos],
        "modes": effective_modes,
        "k_values": k_values,
        "n_notes": len(vault_id_map),
        "n_queries": len(personal_queries),
        "results": results,
    }
    snap = write_snapshot("ablation-personal", payload)
    print(f"\nSnapshot: {snap}")
    return 0
