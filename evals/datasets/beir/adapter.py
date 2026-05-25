from __future__ import annotations

import io
import json
import os
import urllib.request
import zipfile
from pathlib import Path

BEIR_BASE_URL = "https://public.ukp.informatik.tu-darmstadt.de/thakur/BEIR/datasets"

_xdg = os.environ.get("XDG_CACHE_HOME", "").strip()
CACHE_DIR = (
    Path(_xdg) if _xdg else Path.home() / ".cache"
) / "bookmark-tools" / "evals" / "beir"

# Supported datasets: name → {download url, qrels split}
DATASET_INFO: dict[str, dict[str, str]] = {
    "nfcorpus": {
        "url": f"{BEIR_BASE_URL}/nfcorpus.zip",
        "qrels_split": "test",
    },
    "scifact": {
        "url": f"{BEIR_BASE_URL}/scifact.zip",
        "qrels_split": "test",
    },
}


def available_datasets() -> list[str]:
    return sorted(DATASET_INFO)


def _download_and_extract(name: str, cache_dir: Path) -> Path:
    """Download and cache a BEIR dataset zip, returning the dataset directory."""
    info = DATASET_INFO.get(name)
    if not info:
        raise ValueError(
            f"Unknown BEIR dataset {name!r}. Available: {available_datasets()}"
        )
    dest = cache_dir / name
    if dest.exists():
        return dest

    url = info["url"]
    print(f"Downloading BEIR/{name} from {url} ...")
    cache_dir.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url) as resp:  # noqa: S310
        data = resp.read()
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(cache_dir)
    return dest


def load_corpus(dataset_dir: Path) -> list[dict[str, str]]:
    """Load corpus.jsonl → list of {doc_id, title, text}."""
    docs: list[dict[str, str]] = []
    with (dataset_dir / "corpus.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            docs.append(
                {
                    "doc_id": str(obj["_id"]),
                    "title": str(obj.get("title", "")),
                    "text": str(obj.get("text", "")),
                }
            )
    return docs


def load_queries(dataset_dir: Path) -> list[dict[str, str]]:
    """Load queries.jsonl → list of {query_id, text}."""
    queries: list[dict[str, str]] = []
    with (dataset_dir / "queries.jsonl").open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            queries.append({"query_id": str(obj["_id"]), "text": str(obj["text"])})
    return queries


def load_qrels(dataset_dir: Path, split: str = "test") -> dict[str, set[str]]:
    """Load qrels/<split>.tsv → {query_id → set of relevant doc_ids}."""
    qrels: dict[str, set[str]] = {}
    path = dataset_dir / "qrels" / f"{split}.tsv"
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            parts = line.strip().split("\t")
            if len(parts) < 4 or parts[0] in ("query-id", ""):
                continue
            query_id, _iter, doc_id, relevance = parts[:4]
            try:
                if int(relevance) > 0:
                    qrels.setdefault(query_id, set()).add(doc_id)
            except ValueError:
                continue
    return qrels


def load_beir_dataset(
    name: str,
    *,
    cache_dir: Path | None = None,
    query_limit: int | None = None,
) -> tuple[list[dict[str, str]], list[dict[str, str]], dict[str, set[str]]]:
    """Load a BEIR dataset, downloading and caching on first use.

    Returns (corpus, queries, qrels). Only queries that have at least one
    relevance judgment are included. Pass query_limit for quick smoke-tests.
    """
    dataset_dir = _download_and_extract(name, cache_dir or CACHE_DIR)
    info = DATASET_INFO[name]

    corpus = load_corpus(dataset_dir)
    all_queries = load_queries(dataset_dir)
    qrels = load_qrels(dataset_dir, split=info["qrels_split"])

    # Keep only queries with relevance judgments
    queries = [q for q in all_queries if q["query_id"] in qrels]

    if query_limit is not None:
        queries = queries[:query_limit]
        kept = {q["query_id"] for q in queries}
        qrels = {qid: docs for qid, docs in qrels.items() if qid in kept}

    return corpus, queries, qrels
