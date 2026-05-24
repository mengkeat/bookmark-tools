# Phase 3 — Central Provider and Config Discipline

**Date**: 2026-05-24
**Main commit**: `d8eec36`
**Tests**: 312 → 320 (+8 tests)

---

## Goal

Phase 3 prevents provider/model drift by centralizing provider configuration, documenting precedence, and making embedding model/dimension changes visible to search and doctor.

---

## Config resolution

New module: `bookmark_tools/config.py`.

Resolution precedence is now explicit:

1. explicit overrides (intended for command-specific CLI flags),
2. environment variables,
3. `bookmark-tools.toml`,
4. defaults.

TOML discovery order:

1. `BOOKMARK_CONFIG_FILE`,
2. `$VAULT_PATH/Meta/bookmark-tools.toml`,
3. `$VAULT_PATH/bookmark-tools.toml`,
4. `./bookmark-tools.toml`.

Supported TOML sections:

```toml
[provider]
name = "openrouter"
base_url = "https://openrouter.ai/api/v1"
# api_key is supported, but environment variables are preferred for secrets.

[classification]
model = "openai/gpt-4.1-mini"

[summary]
model = "openai/gpt-4.1-mini"

[embedding]
model = "text-embedding-3-small"
dimensions = 256

[timeouts]
request_seconds = 20
summary_seconds = 180
```

---

## Centralized settings

The new `ProviderConfig` dataclass resolves:

- provider name,
- API key,
- OpenAI-compatible base URL,
- classification model,
- summary model,
- embedding model,
- embedding dimensions,
- request timeout,
- summary timeout,
- source config path.

The legacy `get_llm_config()` mapping remains available for existing call sites, but is now backed by `bookmark_tools/config.py`.

---

## Integration points

Updated modules:

- `bookmark_tools/classify.py`
  - `get_llm_config()` now delegates to centralized config.
  - Classification API timeout uses resolved `request_timeout`.

- `bookmark_tools/summarize.py`
  - Direct LLM summary fallback uses `summary_model` when configured.
  - Summary API timeout uses resolved `summary_timeout`.

- `bookmark_tools/embeddings.py`
  - Embedding model and dimensions come from centralized config.
  - API requests send the configured dimensions.
  - Stored rows record the configured model/dimensions.
  - Refresh detects model or dimension drift and re-embeds unchanged notes.
  - Semantic search refuses stores with mismatched model/dimensions and points to `bookmark-rebuild`.

- `bookmark_tools/doctor.py`
  - Embedding drift checks compare stored rows against centrally resolved model/dimensions.

---

## Environment variables

New/preferred variables documented:

- `BOOKMARK_CONFIG_FILE`
- `BOOKMARK_CLASSIFICATION_MODEL`
- `BOOKMARK_SUMMARY_MODEL`
- `BOOKMARK_LLM_PROVIDER`
- `BOOKMARK_EMBEDDING_DIMENSIONS`
- `BOOKMARK_REQUEST_TIMEOUT`
- `BOOKMARK_SUMMARY_TIMEOUT`

Existing compatibility variables remain supported:

- `BOOKMARK_LLM_API_KEY`
- `OPENAI_API_KEY`
- `OPENROUTER_API_KEY`
- `BOOKMARK_LLM_MODEL`
- `OPENAI_MODEL`
- `MODEL_ID`
- `BOOKMARK_LLM_BASE_URL`
- `OPENAI_BASE_URL`
- `LLM_PROVIDER`
- `BOOKMARK_EMBEDDING_MODEL`

---

## Tests added

| Test file | Tests added | Focus |
|---|---:|---|
| `tests/test_config.py` | +5 | TOML reads, env/TOML/override precedence, no-key behavior, invalid dimensions |
| `tests/test_embeddings.py` | +3 | configured dimensions stored, refresh on dimension change, semantic dimension mismatch error |

Total suite after this phase: **320 tests** plus 7 subtests.

---

## Acceptance criteria status

- **Config docs match code**: README and `.env.example` now document TOML discovery, precedence, provider variables, embedding dimensions, and timeouts.
- **Changing embedding dimensions produces a clear doctor/search error**: embedding rows store dimensions, refresh re-embeds on changes, semantic search refuses mismatched dimensions, and doctor reports drift.

---

## Deferred

- `bookmark-providers test` remains optional future work. The config foundation is in place, but active network probing was intentionally left out to keep Phase 3 deterministic and testable without provider credentials.
