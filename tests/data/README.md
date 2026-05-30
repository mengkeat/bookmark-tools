# Test Data: ML-AI Bookmark Dataset

This directory contains a **47-note test dataset** derived from real bookmarks in the `ML-AI/` vault folder, converted to schema v1 format.

## Directory structure

```
tests/data/
├── bookmarks/               # Vault-compatible bookmark notes (schema v1)
│   └── ML-AI/
│       ├── Agents/           # 1 note
│       ├── Computer-Vision/  # 6 notes
│       ├── Diffusion/        # 3 notes
│       ├── General/          # 28 notes
│       ├── LLMs/             # 6 notes
│       └── Reinforcement-Learning/  # 3 notes
├── fixtures.py               # Python helpers for test setup
├── _convert_notes.py         # One-time conversion script (not imported)
└── README.md                 # This file
```

## Data provenance

- **Source:** `~/code/obsidian-vault/Vault/Bookmarks/ML-AI/` (47 markdown notes)
- **Conversion:** Legacy frontmatter upgraded to schema v1 with full field set
- **URL fixes:** Two notes had `url: N/A` and were resolved:
  - `Stanford-CS230` → `https://cs230.stanford.edu/`
  - `JAX-ML-Github-Book` → `https://github.com/jax-ml`

## Schema v1 fields added during conversion

Each note was upgraded from the legacy 11-field frontmatter to the full schema v1 format with 30 fields. Fields not present in the source data were derived:

| Field | Derivation |
|-------|------------|
| `schema_version` | Set to `1` |
| `id` | SHA-256 of normalized URL |
| `final_url`, `canonical_url` | Set to original `url` |
| `domain` | Extracted from URL hostname |
| `added_at` | Same as `created` |
| `last_fetched_at`, `last_success_at` | `created` date with `T00:00:00Z` |
| `status` | `ok` |
| `http_status` | `200` |
| `content_type` | `text/html` |
| `content_hash` | SHA-256 of summary body |
| `classification_prompt_version` | `v1` |
| `source_kind` | `url` |
| Summary body | Wrapped in `<!-- bookmark-tools:summary:start/end -->` blocks |

## Using in tests

```python
from tests.data.fixtures import (
    BOOKMARKS_DIR,
    NOTE_COUNT,
    FOLDERS,
    copy_bookmarks,
    setup_vault,
    all_note_paths,
    all_note_metadata,
    tag_universe,
    type_distribution,
    notes_by_folder,
)

def test_with_real_data(tmp_path):
    vault_dir, bookmarks_dir = setup_vault(tmp_path)
    profile = collect_existing_notes(bookmarks_dir=bookmarks_dir)
    assert len(profile.notes) == NOTE_COUNT  # 47
```

## Regenerating

If the source vault data changes, re-run the conversion:

```bash
uv run python tests/data/_convert_notes.py
```

This reads from `~/code/obsidian-vault/Vault/Bookmarks/ML-AI/` and writes to `tests/data/bookmarks/ML-AI/`.
