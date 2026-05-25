from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from bookmark_tools.tag_normalize import normalize_tags

from evals.datasets.schema_utils import (
    as_string_list,
    ensure_mapping,
    ensure_unique,
    load_yaml,
    optional_text,
    required_text,
    top_level_cases,
)


@dataclass(frozen=True)
class RetrievalQuery:
    """A query that should retrieve the newly ingested bookmark."""

    query: str
    must_be_in_top_k: int


@dataclass(frozen=True)
class E2ECase:
    """One end-to-end ingest + retrieval fixture."""

    case_id: str
    url: str
    html: str
    expected_folder: str
    expected_type: str
    expected_tags: frozenset[str]
    retrieval_queries: tuple[RetrievalQuery, ...]
    allow_new_subfolder: bool


@dataclass(frozen=True)
class E2EDataset:
    """Loaded end-to-end fixture dataset."""

    cases: list[E2ECase]


def _retrieval_query_from_raw(raw: Any, *, context: str) -> RetrievalQuery:
    entry = ensure_mapping(raw, context=context)
    query = required_text(entry, "query", context=context)
    raw_k = entry.get("must_be_in_top_k", 5)
    try:
        top_k = int(raw_k)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{context}: must_be_in_top_k must be an integer") from exc
    if top_k < 1:
        raise ValueError(f"{context}: must_be_in_top_k must be >= 1")
    return RetrievalQuery(query=query, must_be_in_top_k=top_k)


def _retrieval_queries_from_raw(
    value: Any, *, context: str
) -> tuple[RetrievalQuery, ...]:
    if value is None:
        raise ValueError(f"{context}: missing required retrieval_queries field")
    if not isinstance(value, list):
        raise ValueError(f"{context}: expected a list, got {type(value).__name__}")
    queries = tuple(
        _retrieval_query_from_raw(item, context=f"{context}[{index}]")
        for index, item in enumerate(value)
    )
    if not queries:
        raise ValueError(
            f"{context}: retrieval_queries must contain at least one query"
        )
    return queries


def _case_from_raw(raw: Any, *, index: int) -> E2ECase:
    context = f"e2e case {index}"
    entry = ensure_mapping(raw, context=context)
    url = required_text(entry, "url", context=context)
    expected_tags = frozenset(
        normalize_tags(
            list(
                as_string_list(
                    entry.get("expected_tags", []),
                    context=f"{context}.expected_tags",
                )
            )
        )
    )
    if not expected_tags:
        raise ValueError(f"{context}: expected_tags must contain at least one tag")
    return E2ECase(
        case_id=optional_text(entry, "id", f"case-{index + 1}"),
        url=url,
        html=str(entry.get("html", "") or ""),
        expected_folder=required_text(entry, "expected_folder", context=context).strip(
            "/"
        ),
        expected_type=required_text(entry, "expected_type", context=context).lower(),
        expected_tags=expected_tags,
        retrieval_queries=_retrieval_queries_from_raw(
            entry.get("retrieval_queries"), context=f"{context}.retrieval_queries"
        ),
        allow_new_subfolder=bool(entry.get("allow_new_subfolder", False)),
    )


def load_dataset(cases_path: Path) -> E2EDataset:
    """Load end-to-end cases from YAML.

    Supports either a top-level list of cases or a mapping with a `cases` list.
    """
    raw = load_yaml(cases_path)
    case_entries = top_level_cases(raw, path=cases_path)
    cases = [
        _case_from_raw(entry, index=index) for index, entry in enumerate(case_entries)
    ]
    ensure_unique([case.case_id for case in cases], context=f"{cases_path}.cases")
    return E2EDataset(cases=cases)
