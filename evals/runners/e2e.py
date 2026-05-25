from __future__ import annotations

import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from bookmark_tools.tag_normalize import normalize_tags

from evals.datasets.e2e.schema import E2ECase, load_dataset
from evals.runners.classification import (
    aggregate_classification_metrics,
    score_classification_prediction,
    zero_classification_scores,
)
from evals.utils import folder_ancestors, safe_filename_stem

DEFAULT_CASES_PATH = Path(__file__).parent.parent / "datasets" / "e2e" / "cases.yaml"


def _return_none(*_args: object, **_kwargs: object) -> None:
    return None


@contextmanager
def _temporary_env(updates: dict[str, str]) -> Iterator[None]:
    old_values = {key: os.environ.get(key) for key in updates}
    try:
        os.environ.update(updates)
        yield
    finally:
        for key, old_value in old_values.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value


@contextmanager
def _forced_heuristic_pipeline(enabled: bool) -> Iterator[None]:
    """Disable LLM and external summary calls for deterministic smoke tests."""
    if not enabled:
        yield
        return

    import bookmark_tools.cli as cli_module
    import bookmark_tools.summarize as summarize_module

    old_call_llm = cli_module.call_llm
    old_summarize_with_tool = summarize_module.summarize_with_tool
    old_summarize_with_llm = summarize_module.summarize_with_llm
    cli_module.call_llm = _return_none
    summarize_module.summarize_with_tool = _return_none
    summarize_module.summarize_with_llm = _return_none
    try:
        yield
    finally:
        cli_module.call_llm = old_call_llm
        summarize_module.summarize_with_tool = old_summarize_with_tool
        summarize_module.summarize_with_llm = old_summarize_with_llm


def _prepare_bookmark_folders(bookmarks_dir: Path, cases: list[E2ECase]) -> None:
    folders = {"Development"}
    for case in cases:
        folders.update(folder_ancestors(case.expected_folder))
    bookmarks_dir.mkdir(parents=True, exist_ok=True)
    for folder in folders:
        (bookmarks_dir / folder).mkdir(parents=True, exist_ok=True)


def _materialize_html_source(case: E2ECase, sources_dir: Path) -> str:
    sources_dir.mkdir(parents=True, exist_ok=True)
    path = sources_dir / f"{safe_filename_stem(case.case_id)}.html"
    path.write_text(case.html, encoding="utf-8")
    return path.resolve().as_uri()


def _ingest_case(
    case: E2ECase,
    *,
    bookmarks_dir: Path,
    sources_dir: Path,
    force_heuristic: bool,
) -> dict[str, Any]:
    from bookmark_tools.cli import build_note
    from bookmark_tools.note_schema import parse_note_text

    ingest_url = _materialize_html_source(case, sources_dir) if case.html else case.url
    with _forced_heuristic_pipeline(force_heuristic):
        target_path, note_text, folder_message = build_note(
            ingest_url,
            allow_new_subfolder=case.allow_new_subfolder,
            bookmarks_dir=bookmarks_dir,
            source_kind="eval-e2e",
            source_path=str(case.url),
        )
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_path.write_text(note_text, encoding="utf-8")

    note = parse_note_text(note_text, path=target_path)
    predicted_folder = str(target_path.relative_to(bookmarks_dir).parent)
    predicted_folder = "" if predicted_folder == "." else predicted_folder
    raw_tags = note.frontmatter.get("tags", [])
    predicted_tags = (
        set(normalize_tags([str(tag) for tag in raw_tags]))
        if isinstance(raw_tags, list)
        else set()
    )
    predicted_type = str(note.frontmatter.get("type", "")).strip().lower()
    classification_scores = score_classification_prediction(
        predicted_folder=predicted_folder,
        predicted_type=predicted_type,
        predicted_tags=predicted_tags,
        expected_folder=case.expected_folder,
        expected_type=case.expected_type,
        expected_tags=set(case.expected_tags),
    )
    return {
        "id": case.case_id,
        "url": case.url,
        "ingest_url": ingest_url,
        "path": str(target_path),
        "folder_message": folder_message,
        "expected": {
            "folder": case.expected_folder,
            "type": case.expected_type,
            "tags": sorted(case.expected_tags),
        },
        "predicted": {
            "folder": predicted_folder,
            "type": predicted_type,
            "tags": sorted(predicted_tags),
        },
        "classification_scores": classification_scores,
    }


def _run_retrieval_checks(
    cases: list[E2ECase],
    case_results: list[dict[str, Any]],
    *,
    bookmarks_dir: Path,
    db_path: Path,
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    from bookmark_tools.search_documents import collect_search_documents
    from bookmark_tools.search_index import rebuild_search_index, search_index

    successful_paths = {
        result["id"]: Path(str(result["path"]))
        for result in case_results
        if result.get("path")
    }
    if not successful_paths:
        return {}, []

    docs = collect_search_documents(bookmarks_dir=bookmarks_dir)
    rebuild_search_index(docs, database_path=db_path)

    checks: list[dict[str, Any]] = []
    reciprocal_ranks: list[float] = []
    hits = 0
    total = 0
    cases_by_id = {case.case_id: case for case in cases}
    for case_id, target_path in successful_paths.items():
        case = cases_by_id[case_id]
        for retrieval_query in case.retrieval_queries:
            total += 1
            results = search_index(
                retrieval_query.query,
                database_path=db_path,
                limit=retrieval_query.must_be_in_top_k,
            )
            rank = next(
                (
                    index
                    for index, result in enumerate(results, start=1)
                    if result.path == target_path
                ),
                None,
            )
            success = rank is not None and rank <= retrieval_query.must_be_in_top_k
            if success:
                hits += 1
                reciprocal_ranks.append(1.0 / rank)
            else:
                reciprocal_ranks.append(0.0)
            checks.append(
                {
                    "case_id": case_id,
                    "query": retrieval_query.query,
                    "must_be_in_top_k": retrieval_query.must_be_in_top_k,
                    "rank": rank,
                    "success": success,
                }
            )

    metrics = {
        "retrieval_success_rate": hits / total if total else 0.0,
        "retrieval_mrr": sum(reciprocal_ranks) / total if total else 0.0,
        "retrieval_checks": float(total),
    }
    return metrics, checks


def run_e2e(
    *,
    cases_path: Path | None = None,
    limit: int | None = None,
    force_heuristic: bool = False,
) -> int:
    """Run end-to-end ingest fixtures into a temp vault, then test retrieval."""
    from bookmark_tools.config import load_config
    from bookmark_tools.note_schema import CLASSIFICATION_PROMPT_VERSION

    from evals.reporter import _git_info, print_metric_values, write_snapshot

    cases_path = cases_path or DEFAULT_CASES_PATH
    try:
        dataset = load_dataset(cases_path)
    except (OSError, ValueError) as exc:
        print(f"Error loading e2e cases: {exc}", file=sys.stderr)
        return 1

    cases = dataset.cases[: limit or None]
    if not cases:
        print(f"No e2e cases in {cases_path}.")
        return 0

    print(f"Running e2e eval on {len(cases)} case(s) ...")
    case_results: list[dict[str, Any]] = []
    failed = False
    with tempfile.TemporaryDirectory(prefix="bookmark-eval-e2e-") as tmp:
        tmpdir = Path(tmp)
        vault_dir = tmpdir / "Vault"
        bookmarks_dir = vault_dir / "Bookmarks"
        sources_dir = tmpdir / "sources"
        db_path = tmpdir / "search.sqlite3"
        _prepare_bookmark_folders(bookmarks_dir, cases)
        with _temporary_env(
            {"VAULT_PATH": str(vault_dir), "BOOKMARKS_DIR": str(bookmarks_dir)}
        ):
            for case in cases:
                try:
                    result = _ingest_case(
                        case,
                        bookmarks_dir=bookmarks_dir,
                        sources_dir=sources_dir,
                        force_heuristic=force_heuristic,
                    )
                except Exception as exc:  # noqa: BLE001 - evals should report failed cases
                    failed = True
                    result = {
                        "id": case.case_id,
                        "url": case.url,
                        "expected": {
                            "folder": case.expected_folder,
                            "type": case.expected_type,
                            "tags": sorted(case.expected_tags),
                        },
                        "predicted": None,
                        "error": f"{exc.__class__.__name__}: {exc}",
                        "classification_scores": zero_classification_scores(),
                    }
                case_results.append(result)
                predicted = result.get("predicted") or {}
                status = "FAIL" if result.get("error") else "ok"
                print(
                    f"  {case.case_id}: {status} "
                    f"folder={predicted.get('folder', '-')} "
                    f"type={predicted.get('type', '-')}"
                )

            retrieval_metrics, retrieval_checks = _run_retrieval_checks(
                cases,
                case_results,
                bookmarks_dir=bookmarks_dir,
                db_path=db_path,
            )

    classification_metrics = aggregate_classification_metrics(
        [result["classification_scores"] for result in case_results]
    )
    print("\n[classification]")
    print_metric_values(classification_metrics)
    print("\n[retrieval]")
    print_metric_values(retrieval_metrics)

    config = load_config()
    payload: dict[str, Any] = {
        "suite": "e2e",
        "dataset": str(cases_path),
        "git": _git_info(),
        "classification_prompt_version": CLASSIFICATION_PROMPT_VERSION,
        "classification_model": "heuristic"
        if force_heuristic
        else config.classification_model,
        "provider": config.provider,
        "force_heuristic": force_heuristic,
        "n_cases": len(cases),
        "metrics": {
            "classification": classification_metrics,
            "retrieval": retrieval_metrics,
        },
        "cases": case_results,
        "retrieval_checks": retrieval_checks,
    }
    snap = write_snapshot("e2e", payload)
    print(f"\nSnapshot: {snap}")
    return 1 if failed else 0
