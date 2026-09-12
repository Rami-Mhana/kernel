# Kernel repository guidance

Kernel is a YouTube episode archiving and enrichment pipeline for the "الدحيح"
(Al Daheeh) channel and related channels. It fetches metadata, cleans descriptions,
classifies topics, audits uncertain records, and builds a searchable static library.

## Architecture

```text
scripts/fetch_episodes.py       yt-dlp channel metadata -> raw JSONL + CSV
scripts/fetch_descriptions.py   cached episode CSV -> cleaned descriptions
scripts/classification.py       title-first deterministic taxonomy + optional AI fallback
scripts/classify_audit.py       deduplicated, prioritized audit CSV
scripts/build_demo.py           curated CSV + template -> standalone HTML
scripts/content_schema.py       canonical Episode schema and shared cleaning helpers
daheeh-demo.html                 Kernel browser template and local learner dashboard
data/raw/                        local yt-dlp metadata cache (ignored by Git)
```

`video_id` is the stable record key. The generated HTML stores watchlist, status,
notes, profile name, and theme in browser `localStorage`. The profile gate is a
local UX boundary, not authentication or cross-device synchronization.

## Setup on Windows

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## End-to-end workflow

### 1. Fetch metadata

```powershell
python scripts/fetch_episodes.py
```

This reads the `CHANNELS` map or accepts positional YouTube URLs, writes raw JSONL
under `data/raw/`, and creates a UTF-8 BOM CSV. Keep raw JSONL locally; it is
excluded from Git because it is a reproducible cache and can be large.

### 2. Enrich descriptions

```powershell
python scripts/fetch_descriptions.py
```

The script reads `INPUT_CSV`, resumes from `OUTPUT_CSV`, and calls `yt-dlp` only for
records without a cached description. Cleaning is shared with the webapp pipeline:
reference-heavy `#:` sections, URL-only citations, and promotional boilerplate are
removed before the 500-character limit is applied.

### 3. Generate the audit dataset

```powershell
python scripts/classify_audit.py
```

The audit generator:

- Hydrates missing thumbnail, duration, view count, and content metadata from
  `data/raw/*.jsonl` when the legacy input CSV omits those fields.
- Deduplicates by `video_id` (falling back to URL) and keeps the most complete record.
- Preserves manual decisions using `video_id` first, then URL.
- Uses title-first deterministic classification and selects a reproducible
  highest-priority sample.
- Writes `data/episodes_classification_audit.csv` with UTF-8 BOM.

Use `--input`, `--output`, `--sample-size`, `--seed`, and `--raw-dir` to run against
another dataset. Review low confidence, conflicts, missing descriptions, and
uncategorized records before publishing.

### 4. Build the library

```powershell
python scripts/build_demo.py
```

This applies manual classifications from the audit CSV, injects records into
`daheeh-demo.html`, and writes `daheeh-demo-built.html`. Test the generated file in
a browser with RTL layout, keyboard navigation, light/dark/system themes, reduced
motion, invalid import files, and the local profile flow.

## Classification policy

The deterministic classifier is the repeatable source of truth:

1. Extract the meaningful topic from the title.
2. Match specific title patterns and normalized Arabic/English keywords.
3. Use cleaned description text as supporting evidence.
4. Record confidence, rationale, model, and proposed categories.

An optional AI provider may classify only ambiguous records. It must use the existing
allowed taxonomy, return structured JSON, preserve the deterministic result for
comparison, and never write API keys into source code or generated HTML.

## Data and encoding conventions

- Use UTF-8 BOM (`utf-8-sig`) for CSV files containing Arabic text.
- Keep `video_id` in all new pipeline outputs.
- Preserve manual audit fields when regenerating derived CSVs.
- Do not commit `venv/`, `data/raw/`, generated `output/`, secrets, or local editor state.

## Validation

There is no formal test suite. Before committing pipeline changes:

```powershell
$files = Get-ChildItem scripts -Filter *.py | ForEach-Object { $_.FullName }
python -m py_compile $files
git diff --check
python scripts/classify_audit.py
python scripts/build_demo.py
```

For audit changes, also verify row counts, duplicate `video_id` values, populated
thumbnail/duration fields where raw metadata exists, and that no URL-only
descriptions remain.
