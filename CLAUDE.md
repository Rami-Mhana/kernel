# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**dahih-archive** — A YouTube episode archiving and enrichment pipeline for the "الدحيح" (Al Daheeh) channel and related channels. The project fetches video metadata using `yt-dlp`, enriches and audits classifications, then builds a searchable static learning library.

## Architecture

```
dahih-archive/
├── scripts/
│   ├── fetch_episodes.py      # Fetches video metadata from YouTube channels → CSV
│   └── fetch_descriptions.py  # Enriches CSV with video descriptions from YouTube
├── data/
│   ├── raw/                   # Raw JSONL output from yt-dlp (one file per channel)
│   ├── episodes.csv           # Initial merged CSV
│   ├── episodes_3.csv         # Output from fetch_episodes.py
│   ├── episodes_dahih_final.csv / _v2 / _classified_final / _with_desc.csv  # Progressive enrichment stages
└── requirements.txt           # Python dependencies: yt-dlp, pandas
```

## Commands

### Setup
```bash
# Create virtual environment
python -m venv venv
.\venv\Scripts\activate   # Windows PowerShell
pip install -r requirements.txt
```

### Fetch Episodes (metadata only)
```bash
python scripts/fetch_episodes.py
```
- Reads `CHANNELS` dict in the script (edit to add/remove channels)
- Outputs raw JSONL to `data/raw/<channel_name>.jsonl`
- Merges all channels into `data/episodes_3.csv`
- Raw JSONL records retain `id`, `thumbnails`, `duration`, `view_count`, availability, and playlist context.
- Generated episode records use `video_id` as the stable key and include `thumbnail`, `duration_seconds`, and `content_type`.

### Fetch Descriptions (enrichment)

```bash
python scripts/fetch_descriptions.py
```

- Reads `data/episodes_dahih_final_v2.csv` (configure `INPUT_CSV` in script)
- Appends `description` column (truncated to 500 chars, newlines replaced)
- Resumes from `data/episodes_dahih_with_desc.csv` if interrupted
- Rate-limited: 1.5s between requests (`SLEEP_SECONDS`)

### Audit and Build

```powershell
python scripts/classify_audit.py
python scripts/build_demo.py
```

Review `data/episodes_classification_audit.csv` before delivery. Manual classifications override automatic suggestions during the build. Check low-confidence, conflicting, missing-description, duplicate, and uncategorized records rather than publishing an unchecked automated result.

### Static library features

`daheeh-demo.html` is the shared template. It provides thumbnail cards, search, category/type filters, sorting, keyboard-friendly controls, and light/dark/system themes. The Personal Dashboard stores watchlist, in-progress, completed, notes, profile name, and theme locally in the browser. Its JSON export/import is a backup mechanism; it is not secure authentication or cross-device sync.

## Key Files to Modify

| File | Purpose |
| ------ | --------- |
| `scripts/fetch_episodes.py:8-14` | Add/remove YouTube channels in `CHANNELS` dict |
| `scripts/fetch_episodes.py:16-17` | Change `RAW_DIR` or `OUTPUT_CSV` paths |
| `scripts/fetch_descriptions.py:9-11` | Change `INPUT_CSV`, `OUTPUT_CSV`, `SLEEP_SECONDS` |

## Data Flow

1. **Raw fetch**: `yt-dlp --flat-playlist --dump-json <channel_url>` → `data/raw/*.jsonl`
2. **Parse & merge**: JSONL → CSV with standard columns
3. **Manual curation**: User fills `domain`, `watched`, `extracted`, `notes` columns
4. **Description enrichment**: `yt-dlp --skip-download --print "%(description)s" <video_url>` → adds `description` column
5. **Processing and audit**: clean descriptions, propose channel-appropriate categories, and review uncertain records.
6. **Static delivery**: inject the final records into the shared HTML template and test the generated file in a browser.

## Notes

- Requires `yt-dlp` installed and in PATH (included in `requirements.txt`)
- All CSV files use UTF-8 with BOM (`utf-8-sig`) for Arabic text compatibility
- The `study/extraction_template.md` appears to be empty — may be a placeholder for future extraction schemas
- Do not put AI API keys in generated HTML or commit them to the repository.
- Remote YouTube thumbnail URLs require network access; add a local thumbnail-download mode if a fully offline artifact is required.
- No test suite exists; scripts are run manually