from __future__ import annotations

import argparse
import json
import logging
import re
import sqlite3
from dataclasses import dataclass, field as dataclass_field
from pathlib import Path
from typing import Any, Sequence

from .classify import get_llm_config
from .catalog import (
    BOOKMARKS_TABLE as CATALOG_BOOKMARKS_TABLE,
    CATALOG_SCHEMA_VERSION,
    catalog_tables_exist,
    connect as catalog_connect,
    get_catalog_version,
    table_names as catalog_table_names,
)
from .embeddings import EMBEDDING_TABLE, embedding_dimensions, embedding_model
from .note_filter import is_archive_sidecar, iter_bookmark_note_paths
from .note_schema import parse_note_file, validate_schema_v1
from .paths import (
    BookmarkPathError,
    get_search_index_path,
    load_env,
    require_bookmarks_dir,
)
from .search_documents import SearchDocument, collect_search_documents
from .search_index import MTIME_TABLE, SEARCH_TABLE, rebuild_search_index
from .url_normalize import normalize_url

logger = logging.getLogger(__name__)

URL_FIELDS = ("url", "final_url", "canonical_url")
INTERNAL_LINK_RE = re.compile(r"\[\[([^\]|#]+)")


@dataclass
class DoctorIssue:
    """A single doctor finding."""

    code: str
    severity: str
    message: str
    path: str = ""
    field: str = ""
    details: dict[str, Any] = dataclass_field(default_factory=dict)
    fixable: bool = False
    fixed: bool = False

    def to_dict(self) -> dict[str, object]:
        """Return a stable JSON-serializable representation."""
        payload: dict[str, object] = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "path": self.path,
            "field": self.field,
            "fixable": self.fixable,
            "fixed": self.fixed,
        }
        if self.details:
            payload["details"] = self.details
        return payload


@dataclass
class DoctorReport:
    """Complete doctor report."""

    bookmarks_dir: Path | None
    database_path: Path | None
    issues: list[DoctorIssue] = dataclass_field(default_factory=list)

    @property
    def unresolved_issues(self) -> list[DoctorIssue]:
        """Return issues that were not fixed during this run."""
        return [issue for issue in self.issues if not issue.fixed]

    @property
    def errors(self) -> int:
        """Return unresolved error count."""
        return sum(1 for issue in self.unresolved_issues if issue.severity == "error")

    @property
    def warnings(self) -> int:
        """Return unresolved warning count."""
        return sum(1 for issue in self.unresolved_issues if issue.severity == "warning")

    @property
    def fixed_count(self) -> int:
        """Return count of fixed issues."""
        return sum(1 for issue in self.issues if issue.fixed)

    @property
    def status(self) -> str:
        """Return overall health status."""
        if self.errors:
            return "error"
        if self.warnings:
            return "warning"
        return "ok"

    @property
    def score(self) -> int:
        """Return a simple health score from 0 to 100."""
        return max(0, 100 - self.errors * 25 - self.warnings * 10)

    def add_issue(self, issue: DoctorIssue) -> None:
        """Append a doctor issue."""
        self.issues.append(issue)

    def to_dict(self) -> dict[str, object]:
        """Return a stable JSON-serializable report."""
        return {
            "status": self.status,
            "score": self.score,
            "summary": {
                "errors": self.errors,
                "warnings": self.warnings,
                "fixed": self.fixed_count,
                "total": len(self.issues),
            },
            "bookmarks_dir": str(self.bookmarks_dir) if self.bookmarks_dir else "",
            "database_path": str(self.database_path) if self.database_path else "",
            "issues": [issue.to_dict() for issue in self.issues],
        }


def _issue(
    code: str,
    severity: str,
    message: str,
    *,
    path: Path | str | None = None,
    field_name: str = "",
    details: dict[str, Any] | None = None,
    fixable: bool = False,
) -> DoctorIssue:
    """Create a DoctorIssue with normalized path/details defaults."""
    return DoctorIssue(
        code=code,
        severity=severity,
        message=message,
        path=str(path) if path else "",
        field=field_name,
        details=details or {},
        fixable=fixable,
    )


def _markdown_paths(bookmarks_dir: Path) -> list[Path]:
    """Return non-sidecar Markdown files under the bookmarks directory."""
    return sorted(
        path for path in bookmarks_dir.rglob("*.md") if not is_archive_sidecar(path)
    )


def _check_provider(report: DoctorReport) -> None:
    """Validate optional provider availability."""
    if get_llm_config() is None:
        report.add_issue(
            _issue(
                "provider.api_key_missing",
                "warning",
                "No LLM API key configured; classification falls back to heuristics and semantic rebuild/search is unavailable.",
            )
        )


def _check_non_bookmark_markdown(
    report: DoctorReport,
    all_markdown: list[Path],
    bookmark_paths: set[Path],
) -> None:
    """Warn about Markdown files under Bookmarks/ that are not bookmarks."""
    for path in all_markdown:
        if path not in bookmark_paths:
            report.add_issue(
                _issue(
                    "notes.non_bookmark_markdown",
                    "warning",
                    "Markdown file under Bookmarks/ is not a bookmark note.",
                    path=path,
                )
            )


def _check_schema_and_urls(
    report: DoctorReport,
    bookmark_paths: Sequence[Path],
) -> tuple[dict[str, list[dict[str, str]]], set[Path]]:
    """Validate bookmark schemas and collect URL/archive references."""
    url_refs: dict[str, list[dict[str, str]]] = {}
    archive_refs: set[Path] = set()
    bookmarks_dir = report.bookmarks_dir

    for path in bookmark_paths:
        note = parse_note_file(path)
        metadata = note.frontmatter
        for schema_issue in validate_schema_v1(metadata):
            report.add_issue(
                _issue(
                    "schema.invalid",
                    schema_issue.severity,
                    schema_issue.message,
                    path=path,
                    field_name=schema_issue.field,
                )
            )

        seen_for_note: set[str] = set()
        for field_name in URL_FIELDS:
            raw_url = str(metadata.get(field_name, "")).strip()
            normalized = normalize_url(raw_url)
            if not normalized or normalized in seen_for_note:
                continue
            seen_for_note.add(normalized)
            url_refs.setdefault(normalized, []).append(
                {"path": str(path), "field": field_name, "url": raw_url}
            )

        archive_path = str(metadata.get("archive_path", "")).strip()
        if archive_path:
            resolved = _resolve_archive_path(archive_path, path, bookmarks_dir)
            archive_refs.add(resolved)
            if not resolved.exists():
                report.add_issue(
                    _issue(
                        "archive.missing",
                        "warning",
                        "Bookmark references an archive file that does not exist.",
                        path=path,
                        field_name="archive_path",
                        details={"archive_path": str(resolved)},
                    )
                )

    return url_refs, archive_refs


def _resolve_archive_path(
    archive_path: str,
    note_path: Path,
    bookmarks_dir: Path | None,
) -> Path:
    """Resolve an archive_path frontmatter value."""
    candidate = Path(archive_path).expanduser()
    if candidate.is_absolute():
        return candidate
    if bookmarks_dir is not None:
        return bookmarks_dir / candidate
    return note_path.parent / candidate


def _check_duplicate_urls(
    report: DoctorReport,
    url_refs: dict[str, list[dict[str, str]]],
) -> None:
    """Report normalized URLs referenced by more than one bookmark note."""
    for normalized, refs in sorted(url_refs.items()):
        paths = sorted({ref["path"] for ref in refs})
        if len(paths) <= 1:
            continue
        report.add_issue(
            _issue(
                "url.duplicate",
                "error",
                f"Duplicate bookmark URL identity: {normalized}",
                details={"url": normalized, "references": refs},
            )
        )


def _check_archive_sidecars(
    report: DoctorReport,
    archive_refs: set[Path],
) -> None:
    """Warn about archive sidecars not referenced by any bookmark."""
    bookmarks_dir = report.bookmarks_dir
    if bookmarks_dir is None or not bookmarks_dir.exists():
        return
    referenced = {path.resolve() for path in archive_refs if path.exists()}
    for sidecar in sorted(bookmarks_dir.rglob("*.content.md")):
        if sidecar.resolve() not in referenced:
            report.add_issue(
                _issue(
                    "archive.orphan_sidecar",
                    "warning",
                    "Archive sidecar is not referenced by any bookmark note.",
                    path=sidecar,
                )
            )


def _table_names(connection: sqlite3.Connection) -> set[str]:
    """Return all SQLite table names."""
    rows = connection.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return {str(row[0]) for row in rows}


def _check_search_index(
    report: DoctorReport,
    documents: list[SearchDocument],
) -> bool:
    """Check search DB presence, schema, and staleness.

    Returns True when search issues are safe to repair by rebuilding.
    """
    database_path = report.database_path
    if database_path is None:
        return False
    if not database_path.exists():
        report.add_issue(
            _issue(
                "search.missing",
                "warning",
                "Search database is missing and should be rebuilt.",
                path=database_path,
                fixable=True,
            )
        )
        return True

    current_mtimes = {str(doc.path): doc.path.stat().st_mtime for doc in documents}
    stored_mtimes = _read_index_mtimes(report, database_path)
    if stored_mtimes is None:
        # An integrity/schema issue was recorded; a rebuild will repair it.
        return True
    return _report_index_staleness(
        report, database_path, current_mtimes, stored_mtimes
    )


def _read_index_mtimes(
    report: DoctorReport,
    database_path: Path,
) -> dict[str, float] | None:
    """Return stored note mtimes, or None if the index must be rebuilt.

    Records a corruption or schema issue on the report when the database
    fails its integrity check, is missing required tables, or cannot be
    read; in those cases the caller should rebuild.
    """
    try:
        connection = sqlite3.connect(database_path)
        try:
            quick_check = connection.execute("PRAGMA quick_check").fetchone()
            if quick_check and str(quick_check[0]).lower() != "ok":
                report.add_issue(
                    _issue(
                        "search.corrupt",
                        "error",
                        f"SQLite quick_check failed: {quick_check[0]}",
                        path=database_path,
                        fixable=True,
                    )
                )
                return None

            tables = _table_names(connection)
            if SEARCH_TABLE not in tables or MTIME_TABLE not in tables:
                report.add_issue(
                    _issue(
                        "search.schema_missing",
                        "warning",
                        "Search database is missing FTS/mtime tables.",
                        path=database_path,
                        details={
                            "missing_tables": sorted(
                                {SEARCH_TABLE, MTIME_TABLE} - tables
                            )
                        },
                        fixable=True,
                    )
                )
                return None

            rows = connection.execute(
                f"SELECT path, mtime FROM {MTIME_TABLE}"
            ).fetchall()
            return {str(row[0]): float(row[1]) for row in rows}
        finally:
            connection.close()
    except sqlite3.DatabaseError as exc:
        report.add_issue(
            _issue(
                "search.corrupt",
                "error",
                f"Search database could not be read: {exc}",
                path=database_path,
                fixable=True,
            )
        )
        return None


def _report_index_staleness(
    report: DoctorReport,
    database_path: Path,
    current_mtimes: dict[str, float],
    stored_mtimes: dict[str, float],
) -> bool:
    """Compare current vs. indexed mtimes and report any drift.

    Returns True when the index is out of date (notes missing, stale, or
    removed) and should be rebuilt.
    """
    missing = sorted(set(current_mtimes) - set(stored_mtimes))
    removed = sorted(set(stored_mtimes) - set(current_mtimes))
    stale = sorted(
        path
        for path, mtime in current_mtimes.items()
        if path in stored_mtimes and stored_mtimes[path] != mtime
    )

    if missing:
        report.add_issue(
            _issue(
                "search.notes_missing",
                "warning",
                "Bookmark notes are missing from the search index.",
                path=database_path,
                details={"count": len(missing), "paths": missing},
                fixable=True,
            )
        )
    if stale:
        report.add_issue(
            _issue(
                "search.stale",
                "warning",
                "Search index has stale bookmark mtimes.",
                path=database_path,
                details={"count": len(stale), "paths": stale},
                fixable=True,
            )
        )
    if removed:
        report.add_issue(
            _issue(
                "search.removed_notes",
                "warning",
                "Search index contains notes that no longer exist.",
                path=database_path,
                details={"count": len(removed), "paths": removed},
                fixable=True,
            )
        )
    return bool(missing or stale or removed)


def _check_embedding_store(report: DoctorReport) -> bool:
    """Check embedding metadata for model/dimension mismatch.

    Returns True when embedding issues are safe to repair by rebuilding.
    """
    database_path = report.database_path
    if database_path is None or not database_path.exists():
        return False
    try:
        connection = sqlite3.connect(database_path)
        connection.row_factory = sqlite3.Row
        try:
            tables = _table_names(connection)
            if EMBEDDING_TABLE not in tables:
                return False
            columns = {
                str(row["name"])
                for row in connection.execute(f"PRAGMA table_info({EMBEDDING_TABLE})")
            }
            if {"model", "dimensions"} - columns:
                report.add_issue(
                    _issue(
                        "embedding.metadata_missing",
                        "warning",
                        "Embedding table lacks model/dimension metadata.",
                        path=database_path,
                        fixable=get_llm_config() is not None,
                    )
                )
                return True

            config = get_llm_config()
            expected_model = embedding_model(config)
            expected_dimensions = embedding_dimensions(config)
            rows = connection.execute(
                f"SELECT path, model, dimensions FROM {EMBEDDING_TABLE}"
            ).fetchall()
        finally:
            connection.close()
    except sqlite3.DatabaseError:
        return False

    mismatched = [
        {
            "path": str(row["path"]),
            "model": str(row["model"]),
            "dimensions": int(row["dimensions"]),
        }
        for row in rows
        if str(row["model"]) != expected_model
        or int(row["dimensions"]) != expected_dimensions
    ]
    if mismatched:
        report.add_issue(
            _issue(
                "embedding.mismatch",
                "warning",
                "Embedding rows were built with a different model or dimensions.",
                path=database_path,
                details={
                    "expected_model": expected_model,
                    "expected_dimensions": expected_dimensions,
                    "rows": mismatched,
                },
                fixable=get_llm_config() is not None,
            )
        )
        return True
    return False


def _check_internal_links(
    report: DoctorReport,
    all_markdown: list[Path],
) -> None:
    """Check Obsidian-style internal links under the bookmarks directory."""
    bookmarks_dir = report.bookmarks_dir
    if bookmarks_dir is None:
        return
    targets: set[str] = set()
    for path in all_markdown:
        relative_without_suffix = str(path.relative_to(bookmarks_dir).with_suffix(""))
        targets.add(relative_without_suffix)
        targets.add(path.stem)

    for path in all_markdown:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for match in INTERNAL_LINK_RE.finditer(text):
            target = match.group(1).strip()
            if target and target not in targets:
                report.add_issue(
                    _issue(
                        "links.broken_internal",
                        "warning",
                        f"Broken internal Obsidian link: [[{target}]]",
                        path=path,
                        details={"target": target},
                    )
                )


def _check_catalog(
    report: DoctorReport,
    bookmark_paths: Sequence[Path],
) -> bool:
    """Check catalog schema version and bookmark table consistency.

    Returns True when catalog issues are safe to repair by rebuilding.
    """
    database_path = report.database_path
    if database_path is None or not database_path.exists():
        return False

    try:
        connection = catalog_connect(database_path)
    except sqlite3.DatabaseError:
        return False

    try:
        has_tables = catalog_tables_exist(connection)
        if not has_tables:
            # Catalog tables don't exist yet — not an error, just not
            # initialized.  Only warn if FTS tables already exist (meaning
            # the DB is in use but hasn't been upgraded).
            tables = catalog_table_names(connection)
            if SEARCH_TABLE in tables:
                report.add_issue(
                    _issue(
                        "catalog.not_initialized",
                        "warning",
                        "Database has search tables but no catalog metadata. "
                        "Run bookmark-rebuild --catalog to initialize.",
                        path=database_path,
                        fixable=True,
                    )
                )
                return True
            return False

        version = get_catalog_version(connection)
        if version != CATALOG_SCHEMA_VERSION:
            report.add_issue(
                _issue(
                    "catalog.version_mismatch",
                    "warning",
                    f"Catalog schema version is {version}, expected {CATALOG_SCHEMA_VERSION}. "
                    "Run bookmark-rebuild --catalog to upgrade.",
                    path=database_path,
                    details={
                        "current_version": version,
                        "expected_version": CATALOG_SCHEMA_VERSION,
                    },
                    fixable=True,
                )
            )
            return True

        # Check bookmark count consistency
        try:
            catalog_count_row = connection.execute(
                f"SELECT COUNT(*) FROM {CATALOG_BOOKMARKS_TABLE}"
            ).fetchone()
            catalog_count = int(catalog_count_row[0]) if catalog_count_row else 0
        except sqlite3.OperationalError:
            catalog_count = 0

        note_count = len(bookmark_paths)

        if catalog_count != note_count:
            report.add_issue(
                _issue(
                    "catalog.bookmark_count_mismatch",
                    "warning",
                    "Catalog bookmark count does not match vault note count.",
                    path=database_path,
                    details={
                        "catalog_count": catalog_count,
                        "note_count": note_count,
                    },
                    fixable=True,
                )
            )
            return True

        # Check for orphaned catalog rows (notes that no longer exist)
        if catalog_count > 0:
            note_path_set = {str(p) for p in bookmark_paths}
            orphaned_rows = (
                connection.execute(
                    f"SELECT note_path FROM {CATALOG_BOOKMARKS_TABLE} "
                    f"WHERE note_path NOT IN ({','.join('?' * len(note_path_set))})",
                    list(note_path_set),
                ).fetchall()
                if note_path_set
                else []
            )
            if orphaned_rows:
                report.add_issue(
                    _issue(
                        "catalog.orphaned_rows",
                        "warning",
                        "Catalog contains entries for notes that no longer exist.",
                        path=database_path,
                        details={
                            "count": len(orphaned_rows),
                            "paths": [str(row[0]) for row in orphaned_rows[:10]],
                        },
                        fixable=True,
                    )
                )
                return True

    except sqlite3.DatabaseError:
        return False
    finally:
        connection.close()

    return False


def _apply_fixes(
    report: DoctorReport,
    *,
    documents: list[SearchDocument],
    bookmarks_dir: Path | None,
    fix_search: bool,
    fix_embeddings: bool,
    fix_catalog: bool,
) -> None:
    """Apply safe doctor repairs."""
    database_path = report.database_path
    if database_path is None:
        return

    if fix_catalog:
        try:
            from .catalog import rebuild_catalog

            config = get_llm_config()
            rebuild_catalog(
                bookmarks_dir=bookmarks_dir,
                database_path=database_path,
                include_embeddings=bool(config),
                embedding_config=config,
            )
        except (OSError, sqlite3.DatabaseError, ValueError) as exc:
            report.add_issue(
                _issue(
                    "fix.catalog_failed",
                    "error",
                    f"Failed to rebuild catalog: {exc}",
                    path=database_path,
                )
            )
        else:
            for issue in report.issues:
                if issue.code.startswith("catalog.") and issue.fixable:
                    issue.fixed = True
            # Catalog rebuild also fixes search and embedding issues
            for issue in report.issues:
                if issue.code.startswith("search.") and issue.fixable:
                    issue.fixed = True
                if issue.code.startswith("embedding.") and issue.fixable:
                    issue.fixed = True
            report.add_issue(
                _issue(
                    "fix.catalog_rebuilt",
                    "info",
                    "Rebuilt unified catalog from bookmark Markdown.",
                    path=database_path,
                )
            )
            report.issues[-1].fixed = True
            # Skip individual search/embedding fixes when catalog was rebuilt
            return

    if fix_search:
        try:
            if any(issue.code == "search.corrupt" for issue in report.issues):
                database_path.unlink(missing_ok=True)
            rebuild_search_index(documents, database_path=database_path)
        except (OSError, sqlite3.DatabaseError) as exc:
            report.add_issue(
                _issue(
                    "fix.search_failed",
                    "error",
                    f"Failed to rebuild search index: {exc}",
                    path=database_path,
                )
            )
        else:
            for issue in report.issues:
                if issue.code.startswith("search.") and issue.fixable:
                    issue.fixed = True
            report.add_issue(
                _issue(
                    "fix.search_rebuilt",
                    "info",
                    "Rebuilt search index from bookmark Markdown.",
                    path=database_path,
                )
            )
            report.issues[-1].fixed = True

    if fix_embeddings:
        config = get_llm_config()
        if not config:
            report.add_issue(
                _issue(
                    "fix.embeddings_skipped",
                    "warning",
                    "Cannot rebuild embeddings because no LLM API key is configured.",
                    path=database_path,
                )
            )
            return
        try:
            from .embeddings import rebuild_embeddings

            rebuild_embeddings(documents, database_path=database_path, config=config)
        except (ValueError, OSError, sqlite3.DatabaseError) as exc:
            report.add_issue(
                _issue(
                    "fix.embeddings_failed",
                    "error",
                    f"Failed to rebuild embeddings: {exc}",
                    path=database_path,
                )
            )
        else:
            for issue in report.issues:
                if issue.code.startswith("embedding.") and issue.fixable:
                    issue.fixed = True
            report.add_issue(
                _issue(
                    "fix.embeddings_rebuilt",
                    "info",
                    "Rebuilt embedding store from bookmark Markdown.",
                    path=database_path,
                )
            )
            report.issues[-1].fixed = True


def run_doctor(
    *,
    bookmarks_dir: Path | None = None,
    database_path: Path | None = None,
    fix: bool = False,
) -> DoctorReport:
    """Run bookmark health checks and optionally apply safe fixes."""
    resolved_database = database_path or get_search_index_path()
    try:
        resolved_bookmarks = bookmarks_dir or require_bookmarks_dir()
    except BookmarkPathError as exc:
        report = DoctorReport(bookmarks_dir=None, database_path=resolved_database)
        report.add_issue(_issue("config.bookmarks_dir", "error", str(exc)))
        return report

    report = DoctorReport(
        bookmarks_dir=resolved_bookmarks,
        database_path=resolved_database,
    )
    if not resolved_bookmarks.exists():
        report.add_issue(
            _issue(
                "config.bookmarks_dir_missing",
                "error",
                f"Bookmarks directory does not exist: {resolved_bookmarks}",
                path=resolved_bookmarks,
            )
        )
        return report
    if not resolved_bookmarks.is_dir():
        report.add_issue(
            _issue(
                "config.bookmarks_dir_not_directory",
                "error",
                f"Bookmarks path is not a directory: {resolved_bookmarks}",
                path=resolved_bookmarks,
            )
        )
        return report

    _check_provider(report)

    all_markdown = _markdown_paths(resolved_bookmarks)
    bookmark_paths = list(
        iter_bookmark_note_paths(resolved_bookmarks, bookmark_only=True)
    )
    bookmark_path_set = set(bookmark_paths)
    _check_non_bookmark_markdown(report, all_markdown, bookmark_path_set)
    url_refs, archive_refs = _check_schema_and_urls(report, bookmark_paths)
    _check_duplicate_urls(report, url_refs)
    _check_archive_sidecars(report, archive_refs)
    _check_internal_links(report, all_markdown)

    documents = collect_search_documents(bookmarks_dir=resolved_bookmarks)
    search_needs_fix = _check_search_index(report, documents)
    embeddings_need_fix = _check_embedding_store(report)
    catalog_needs_fix = _check_catalog(report, bookmark_paths)

    if fix:
        _apply_fixes(
            report,
            documents=documents,
            bookmarks_dir=resolved_bookmarks,
            fix_search=search_needs_fix,
            fix_embeddings=embeddings_need_fix,
            fix_catalog=catalog_needs_fix,
        )

    return report


def format_report_text(report: DoctorReport) -> str:
    """Format a human-readable doctor report."""
    lines = [
        f"Bookmark doctor: {report.status.upper()} (score {report.score}/100)",
        f"Bookmarks: {report.bookmarks_dir or '(not configured)'}",
        f"Search DB: {report.database_path or '(not configured)'}",
        f"Issues: {report.errors} error(s), {report.warnings} warning(s), {report.fixed_count} fixed",
    ]
    if not report.issues:
        lines.append("No issues found.")
        return "\n".join(lines)

    lines.append("")
    for issue in report.issues:
        status = "fixed" if issue.fixed else issue.severity
        location = f" [{issue.path}]" if issue.path else ""
        field_text = f" field={issue.field}" if issue.field else ""
        lines.append(
            f"- {status.upper()} {issue.code}{location}{field_text}: {issue.message}"
        )
    return "\n".join(lines)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for bookmark-doctor."""
    parser = argparse.ArgumentParser(
        description="Diagnose bookmark vault and derived-state health."
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="Print a stable JSON report",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Apply safe repairs such as rebuilding derived indexes",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging output",
    )
    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Suppress all logging output except errors",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    """Run bookmark-doctor."""
    load_env()
    args = parse_args(argv)
    from .logging_config import configure_logging

    configure_logging(verbose=args.verbose, quiet=args.quiet)
    report = run_doctor(fix=args.fix)
    if args.json_output:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_report_text(report))
    return 1 if report.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
