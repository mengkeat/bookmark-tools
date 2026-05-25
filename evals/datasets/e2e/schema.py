from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


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


def _as_mapping(value: Any, *, context: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError(f"{context}: expected a mapping, got {type(value).__name__}")
    return value


def _as_string_list(value: Any, *, context: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ValueError(f"{context}: expected a list, got {type(value).__name__}")
    items: list[str] = []
    for index, item in enumerate(value):
        text = str(item).strip()
        if not text:
            raise ValueError(f"{context}[{index}]: empty value")
        items.append(text)
    return tuple(items)


def _optional_text(entry: dict[str, Any], key: str, default: str = "") -> str:
    value = entry.get(key, default)
    if value is None:
        return default
    return str(value).strip()


def _required_text(entry: dict[str, Any], key: str, *, context: str) -> str:
    text = _optional_text(entry, key)
    if not text:
        raise ValueError(f"{context}: missing required {key!r} field")
    return text


def _retrieval_query_from_raw(raw: Any, *, context: str) -> RetrievalQuery:
    entry = _as_mapping(raw, context=context)
    query = _required_text(entry, "query", context=context)
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
    entry = _as_mapping(raw, context=context)
    url = _required_text(entry, "url", context=context)
    expected_tags = frozenset(
        tag.lower()
        for tag in _as_string_list(
            entry.get("expected_tags", []), context=f"{context}.expected_tags"
        )
    )
    if not expected_tags:
        raise ValueError(f"{context}: expected_tags must contain at least one tag")
    return E2ECase(
        case_id=_optional_text(entry, "id", f"case-{index + 1}"),
        url=url,
        html=str(entry.get("html", "") or ""),
        expected_folder=_required_text(entry, "expected_folder", context=context).strip(
            "/"
        ),
        expected_type=_required_text(entry, "expected_type", context=context).lower(),
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
    raw = yaml.safe_load(cases_path.read_text(encoding="utf-8"))
    if raw is None:
        return E2EDataset(cases=[])
    if isinstance(raw, list):
        case_entries = raw
    elif isinstance(raw, dict):
        case_entries = raw.get("cases", [])
        if not isinstance(case_entries, list):
            raise ValueError(
                f"{cases_path}: 'cases' must be a list, got {type(case_entries).__name__}"
            )
    else:
        raise ValueError(
            f"{cases_path}: expected a YAML list or mapping, got {type(raw).__name__}"
        )
    return E2EDataset(
        cases=[
            _case_from_raw(entry, index=index)
            for index, entry in enumerate(case_entries)
        ]
    )
