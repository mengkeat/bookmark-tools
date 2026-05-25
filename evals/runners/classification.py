from __future__ import annotations

import hashlib
import re
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from evals.datasets.classification.schema import (
    ClassificationCase,
    ClassificationDataset,
    ProfileNoteSeed,
    load_dataset,
)

DEFAULT_FIXTURES_PATH = (
    Path(__file__).parent.parent / "datasets" / "classification" / "fixtures.yaml"
)


def score_classification_prediction(
    *,
    predicted_folder: str,
    predicted_type: str,
    predicted_tags: set[str],
    expected_folder: str,
    expected_type: str,
    expected_tags: set[str],
) -> dict[str, float]:
    """Score one classification prediction against exact folder/type and tag F1."""
    tag_hits = len(predicted_tags & expected_tags)
    tag_precision = tag_hits / len(predicted_tags) if predicted_tags else 0.0
    tag_recall = tag_hits / len(expected_tags) if expected_tags else 0.0
    tag_f1 = (
        (2 * tag_precision * tag_recall) / (tag_precision + tag_recall)
        if tag_precision + tag_recall
        else 0.0
    )
    return {
        "folder_accuracy": 1.0 if predicted_folder == expected_folder else 0.0,
        "type_accuracy": 1.0 if predicted_type == expected_type else 0.0,
        "tag_precision": tag_precision,
        "tag_recall": tag_recall,
        "tag_f1": tag_f1,
    }


def aggregate_classification_metrics(
    scores: list[dict[str, float]],
) -> dict[str, float]:
    """Macro-average classification scores."""
    if not scores:
        return {}
    keys = scores[0].keys()
    n = len(scores)
    return {key: sum(score[key] for score in scores) / n for key in keys}


def print_classification_metrics(metrics: dict[str, float]) -> None:
    """Print a compact classification metric table."""
    if not metrics:
        print("No metrics.")
        return
    metric_col = max(len(key) for key in metrics) + 2
    print("metric".ljust(metric_col) + "value")
    print("-" * (metric_col + 8))
    for key, value in metrics.items():
        print(f"{key.ljust(metric_col)}{value:.4f}")


def _safe_stem(text: str) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", text.strip()).strip("-").lower()
    if not stem:
        stem = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return stem[:120]


def _write_seed_note(bookmarks_dir: Path, note: ProfileNoteSeed, index: int) -> None:
    from bookmark_tools.note_schema import yaml_scalar

    folder = note.folder.strip("/") or "Development"
    folder_path = bookmarks_dir / folder
    folder_path.mkdir(parents=True, exist_ok=True)
    note_path = folder_path / f"{_safe_stem(note.title) or f'profile-{index}'}.md"
    tags = "[" + ", ".join(note.tags) + "]"
    note_path.write_text(
        "\n".join(
            [
                "---",
                f"title: {yaml_scalar(note.title)}",
                f"url: {yaml_scalar(note.url)}",
                f"type: {yaml_scalar(note.bookmark_type)}",
                f"tags: {tags}",
                "language: en",
                f"related: {tags}",
                f"parent_topic: {yaml_scalar(note.parent_topic)}",
                "visibility: private",
                f"description: {yaml_scalar(note.description)}",
                "---",
                "",
                note.description,
                "",
            ]
        ),
        encoding="utf-8",
    )


def _folder_parts(folder: str) -> list[str]:
    parts = [part for part in folder.strip("/").split("/") if part]
    return ["/".join(parts[: index + 1]) for index in range(len(parts))]


def _build_synthetic_profile(
    bookmarks_dir: Path,
    dataset: ClassificationDataset,
    cases: list[ClassificationCase],
) -> None:
    folders: set[str] = {"Development"}
    for folder in dataset.profile_folders:
        folders.update(_folder_parts(folder))
    for note in dataset.profile_notes:
        folders.update(_folder_parts(note.folder))
    for case in cases:
        folders.update(_folder_parts(case.expected_folder))
        for folder in case.profile_folders:
            folders.update(_folder_parts(folder))
        for note in case.profile_notes:
            folders.update(_folder_parts(note.folder))

    bookmarks_dir.mkdir(parents=True, exist_ok=True)
    for folder in folders:
        (bookmarks_dir / folder).mkdir(parents=True, exist_ok=True)

    seed_notes = list(dataset.profile_notes)
    for case in cases:
        seed_notes.extend(case.profile_notes)
    for index, note in enumerate(seed_notes):
        _write_seed_note(bookmarks_dir, note, index)


def _page_data_for_case(case: ClassificationCase):
    from bookmark_tools.fetch import clean_html, extract_page_data

    if case.url and not (case.content or case.html):
        return extract_page_data(case.url)

    raw_content = clean_html(case.html) if case.html else case.content
    title = case.title or raw_content[:80].strip() or case.case_id
    description = case.description or raw_content[:180].strip() or title
    url = case.url or f"urn:classification:{case.case_id}"
    content_type = "text/html" if case.html else "text/plain"
    return {
        "url": url,
        "final_url": url,
        "canonical_url": url,
        "title": title,
        "description": description,
        "language": case.language or "en",
        "content": raw_content[:8000],
        "full_content": raw_content,
        "http_status": 200,
        "content_type": content_type,
    }


def _classify_case(
    case: ClassificationCase,
    *,
    profile,
    bookmarks_dir: Path,
    force_heuristic: bool,
) -> dict[str, Any]:
    from bookmark_tools.classify import (
        call_llm,
        heuristic_classification,
        rank_similar_notes,
        validate_folder,
    )
    from bookmark_tools.cli import normalize_metadata

    page_data = _page_data_for_case(case)
    similar_notes = rank_similar_notes(page_data, profile)
    llm_metadata = (
        None
        if force_heuristic
        else call_llm(
            page_data,
            profile,
            similar_notes,
            case.allow_new_subfolder,
        )
    )
    metadata = llm_metadata or heuristic_classification(
        page_data, profile, similar_notes
    )
    folder, folder_message = validate_folder(
        str(metadata.get("folder", "Development")),
        case.allow_new_subfolder,
        bookmarks_dir=bookmarks_dir,
    )
    normalized = normalize_metadata(
        metadata,
        page_data,
        folder,
        profile,
        similar_notes,
        used_llm_classification=llm_metadata is not None,
    )
    predicted_tags = {str(tag).lower() for tag in normalized["tags"]}
    expected_tags = set(case.expected_tags)
    score = score_classification_prediction(
        predicted_folder=normalized["folder"],
        predicted_type=normalized["type"],
        predicted_tags=predicted_tags,
        expected_folder=case.expected_folder,
        expected_type=case.expected_type,
        expected_tags=expected_tags,
    )
    return {
        "id": case.case_id,
        "expected": {
            "folder": case.expected_folder,
            "type": case.expected_type,
            "tags": sorted(expected_tags),
        },
        "predicted": {
            "folder": normalized["folder"],
            "type": normalized["type"],
            "tags": sorted(predicted_tags),
        },
        "used_llm": llm_metadata is not None,
        "folder_message": folder_message,
        "scores": score,
    }


def run_classification(
    *,
    fixtures_path: Path | None = None,
    limit: int | None = None,
    bookmarks_dir: Path | None = None,
    force_heuristic: bool = False,
) -> int:
    """Run classification fixtures and write an eval snapshot."""
    from bookmark_tools.config import load_config
    from bookmark_tools.note_schema import CLASSIFICATION_PROMPT_VERSION
    from bookmark_tools.vault_profile import collect_existing_notes

    from evals.reporter import _git_info, write_snapshot

    fixtures_path = fixtures_path or DEFAULT_FIXTURES_PATH
    try:
        dataset = load_dataset(fixtures_path)
    except (OSError, ValueError) as exc:
        print(f"Error loading classification fixtures: {exc}", file=sys.stderr)
        return 1

    cases = dataset.cases[: limit or None]
    if not cases:
        print(f"No classification fixtures in {fixtures_path}.")
        return 0

    with ExitStack() as stack:
        if bookmarks_dir is None:
            tmpdir = Path(
                stack.enter_context(
                    tempfile.TemporaryDirectory(prefix="bookmark-eval-classification-")
                )
            )
            profile_bookmarks_dir = tmpdir / "Bookmarks"
            _build_synthetic_profile(profile_bookmarks_dir, dataset, cases)
        else:
            profile_bookmarks_dir = bookmarks_dir

        profile = collect_existing_notes(bookmarks_dir=profile_bookmarks_dir)
        print(f"Running classification eval on {len(cases)} fixture(s) ...")
        print(f"Profile: {len(profile.notes)} notes | {len(profile.folders)} folders")

        case_results: list[dict[str, Any]] = []
        failed = False
        for case in cases:
            try:
                result = _classify_case(
                    case,
                    profile=profile,
                    bookmarks_dir=profile_bookmarks_dir,
                    force_heuristic=force_heuristic,
                )
            except Exception as exc:  # noqa: BLE001 - evals should report failed cases
                failed = True
                result = {
                    "id": case.case_id,
                    "expected": {
                        "folder": case.expected_folder,
                        "type": case.expected_type,
                        "tags": sorted(case.expected_tags),
                    },
                    "predicted": None,
                    "used_llm": False,
                    "error": f"{exc.__class__.__name__}: {exc}",
                    "scores": {
                        "folder_accuracy": 0.0,
                        "type_accuracy": 0.0,
                        "tag_precision": 0.0,
                        "tag_recall": 0.0,
                        "tag_f1": 0.0,
                    },
                }
            case_results.append(result)
            predicted = result.get("predicted") or {}
            status = "FAIL" if result.get("error") else "ok"
            print(
                f"  {case.case_id}: {status} "
                f"folder={predicted.get('folder', '-')} "
                f"type={predicted.get('type', '-')} "
                f"tag_f1={result['scores']['tag_f1']:.3f}"
            )

    metrics = aggregate_classification_metrics([r["scores"] for r in case_results])
    print()
    print_classification_metrics(metrics)

    config = load_config()
    payload: dict[str, Any] = {
        "suite": "classification",
        "dataset": str(fixtures_path),
        "git": _git_info(),
        "classification_prompt_version": CLASSIFICATION_PROMPT_VERSION,
        "classification_model": "heuristic"
        if force_heuristic
        else config.classification_model,
        "provider": config.provider,
        "force_heuristic": force_heuristic,
        "n_cases": len(cases),
        "metrics": metrics,
        "cases": case_results,
    }
    snap = write_snapshot("classification", payload)
    print(f"\nSnapshot: {snap}")
    return 1 if failed else 0
