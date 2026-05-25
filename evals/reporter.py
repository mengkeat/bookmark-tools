from __future__ import annotations

import datetime
import json
import subprocess
from pathlib import Path

RESULTS_DIR = Path(__file__).parent / "results"


def _git_info() -> dict[str, object]:
    try:
        sha = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
        dirty = bool(
            subprocess.check_output(
                ["git", "status", "--porcelain"], text=True, stderr=subprocess.DEVNULL
            ).strip()
        )
        return {"sha": sha[:12], "dirty": dirty}
    except Exception:
        return {"sha": "unknown", "dirty": False}


def write_snapshot(
    run_id: str,
    payload: dict[str, object],
    *,
    results_dir: Path | None = None,
) -> Path:
    """Write a JSON eval snapshot and return its path."""
    dir_ = results_dir or RESULTS_DIR
    dir_.mkdir(parents=True, exist_ok=True)
    ts = datetime.datetime.now(datetime.UTC).strftime("%Y%m%dT%H%M%SZ")
    path = dir_ / f"{ts}__{run_id}.json"
    path.write_text(json.dumps(payload, indent=2))
    return path


def print_metrics_table(
    metrics_by_mode: dict[str, dict[str, float]],
    k_values: list[int],
) -> None:
    """Print a formatted table of metrics to stdout."""
    metric_keys = (
        [f"p@{k}" for k in k_values]
        + [f"recall@{k}" for k in k_values]
        + ["mrr"]
        + [f"ndcg@{k}" for k in k_values]
    )
    col = 10
    header = "mode".ljust(col) + "  " + "  ".join(k.ljust(col) for k in metric_keys)
    print(header)
    print("-" * len(header))
    for mode, m in metrics_by_mode.items():
        row = mode.ljust(col) + "  " + "  ".join(
            f"{m.get(key, 0.0):.4f}".ljust(col) for key in metric_keys
        )
        print(row)


def diff_snapshots(baseline: Path, current: Path) -> None:
    """Print a delta table comparing two snapshot files."""
    a = json.loads(baseline.read_text())
    b = json.loads(current.read_text())
    a_modes = a.get("metrics_by_mode", {})
    b_modes = b.get("metrics_by_mode", {})
    all_modes = sorted(set(a_modes) | set(b_modes))
    all_keys = sorted(
        {k for m in list(a_modes.values()) + list(b_modes.values()) for k in m}
    )
    col = 12
    header = "mode".ljust(col) + "  " + "  ".join(k.ljust(col) for k in all_keys)
    print(f"baseline : {baseline.name}")
    print(f"current  : {current.name}")
    print(header)
    print("-" * len(header))
    for mode in all_modes:
        a_m = a_modes.get(mode, {})
        b_m = b_modes.get(mode, {})
        parts = [
            f"{'+'if (b_m.get(k,0.0)-a_m.get(k,0.0))>=0 else ''}{b_m.get(k,0.0)-a_m.get(k,0.0):.4f}".ljust(col)
            for k in all_keys
        ]
        print(mode.ljust(col) + "  " + "  ".join(parts))
