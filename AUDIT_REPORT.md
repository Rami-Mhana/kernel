# dahih-archive — Codebase Audit Report

**Date:** 2026-08-26  
**Auditor:** Claude Code  
**Scope:** Full pipeline — fetch, enrich, classify, audit, build, template

---

## 🔴 Critical Issues (Must Fix)

### 1. **Encoding Corruption in Built HTML**
- **File:** `scripts/build_demo.py:143-156`
- **Problem:** Arabic text in template title/meta replaced with Unicode escape sequences (`Ø¯Ø­Ø§` instead of `دحيح`)
- **Root Cause:** JSON encoding with `ensure_ascii=False` but then `.replace("<", "\\u003c")` etc. corrupts UTF-8
- **Impact:** Built HTML shows garbled text in browser tab, meta tags, and any injected content

### 2. **Description Cleaning Not Working**
- **File:** `scripts/fetch_descriptions.py` + `content_schema.py:338-372`
- **Problem:** Raw descriptions contain promotional boilerplate (University links, social media, sponsor text) that `clean_description_for_classification` should strip but doesn't
- **Evidence:** CSV shows `"University application link https://sut.edu.eg/apply-now"` in descriptions
- **Root Cause:** `fetch_descriptions.py` truncates at 500 chars *before* cleaning, and cleaning patterns don't match Arabic promotional text

### 3. **Classification Failing — Everything Falls to "عام / متنوع"**
- **File:** `classification.py:238-310` (`classify_deterministic`)
- **Problem:** 90%+ episodes classified as "عام / متنوع" with 0.1-0.2 confidence
- **Root Causes:**
  - Keywords are Arabic but descriptions are mostly English references
  - Series patterns (`SERIES_PATTERNS`) only match "دحيح | Category" format, not actual titles
  - `normalize_arabic_text` strips diacritics but keywords include them
  - No fallback to title-based classification when description is mostly references

### 4. **Duplicate Entries in Audit CSV**
- **File:** `data/episodes_classification_audit.csv`
- **Problem:** Same `video_id` appears multiple times (e.g., `-fyJk0JBG4k` twice)
- **Root Cause:** `select_audit_sample` doesn't deduplicate before sampling

### 5. **Missing Duration & Thumbnail Data in Audit CSV**
- **File:** `classify_audit.py:280-312` (`generate_audit_csv`)
- **Problem:** `duration_string` and `thumbnail_url` columns empty for many rows
- **Root Cause:** Source CSV (`episodes_dahih_with_desc.csv`) lacks these fields; `load_episodes_from_csv` doesn't fetch from raw JSONL

### 6. **fetch_episodes.py Output Schema Mismatch**
- **File:** `scripts/fetch_episodes.py:41-63` (`parse_jsonl`)
- **Problem:** Outputs minimal fields (title, url, channel, domain, watched, extracted, notes) — missing `video_id`, `duration`, `thumbnail`, `view_count`, `content_type`
- **Impact:** Downstream scripts must re-fetch or infer missing data

---

## 🟡 High Priority Issues

### 7. **No Video ID Extraction in fetch_episodes.py**
- `parse_jsonl` constructs URL from `data.get('id')` but doesn't store `video_id` column
- Downstream: `content_schema.py:113-117` must regex-extract from URL — fragile

### 8. **Thumbnail Selection Not Using Shared Module**
- `build_demo.py` and `channel_to_webapp.py` don't use `thumbnail.py` utilities
- No fallback chain for broken thumbnails in generated HTML
- Shorts get landscape thumbnails (wrong aspect ratio)

### 9. **Audit Sampling Not Reproducible Across Runs**
- `classify_audit.py:249` uses `random.seed(seed)` but `random.choices` with weights can vary if pool changes
- Should use deterministic selection (e.g., top-N by priority score)

### 10. **Channel-to-Webapp Pipeline Duplicates Logic**
- `channel_to_webapp.py` reimplements fetch, parse, enrich, classify, build
- Should compose shared modules (`content_schema`, `classification`, `thumbnail`, `build_demo`)

### 11. **No Validation of Generated HTML**
- No dry-run / smoke test for generated HTML
- No check for: valid JSON injection, Arabic rendering, thumbnail URLs, empty states

---

## 🟢 Medium Priority Issues

### 12. **Template: Theme System Incomplete**
- **File:** `daheeh-demo.html:29-41`
- **Problem:** `data-theme="system"` uses `@media (prefers-color-scheme)` but no explicit `light`/`dark`/`system` toggle persistence
- **Missing:** `data-theme="light"` and `data-theme="dark"` explicit rules (only `:root` defaults and `html[data-theme="dark"]`)

### 13. **Template: No Keyboard Navigation for Filter Chips**
- Filter chips are `<button role="tab">` but no arrow-key navigation, no `Home`/`End`, no `Tab` management

### 14. **Template: Search Input Not Announced to Screen Readers**
- `role="search"` on container but no `aria-live` region for result count updates
- No "X results found" announcement

### 15. **Template: Dashboard Import/Export No Validation**
- Import accepts any JSON, no schema validation, no version check
- Export filename not timestamped

### 16. **Template: Profile Dialog Not Fully Accessible**
- `role="dialog"` but no `aria-labelledby` pointing to title (has `aria-labelledby="profileDialogTitle"` but title is `<h2 id="profileDialogTitle">` — actually OK)
- Missing: focus trap, `Escape` to close, focus return to trigger

### 17. **Missing requirements for AI Classification**
- `requirements.txt` only has `yt-dlp`, `pandas` — missing `openai`, `anthropic`, `google-generativeai`
- AI classification code exists but will fail at runtime

### 18. **No Tests or CI**
- No unit tests for classification, schema, thumbnail selection
- No GitHub Actions for lint, type-check, build verification

---

## 🔵 Low Priority / Nice to Have

### 19. **Documentation Gaps**
- `CLAUDE.md` references `study/extraction_template.md` which is empty
- `README.md` shows old `fetch_episodes.py` CLI (positional args) but script uses `argparse`
- No `CONTRIBUTING.md` or `ARCHITECTURE.md`

### 20. **Thumbnail Download Mode**
- `thumbnail.py:228-242` has `validate_thumbnail_url` but no batch download for offline use
- Template uses remote YouTube URLs — fails offline

### 21. **Performance: Re-renders Entire DOM on Filter**
- `renderAll()` rebuilds all category sections from scratch
- Should use virtual scrolling or DOM diffing for 1000+ episodes

### 22. **Accessibility: Color Contrast**
- Accent colors (`#c0392b` on white, `#e05242` on dark) may not meet WCAG AA for small text
- Should verify with contrast checker

---

## 📋 Recommended Fix Order

| Phase | Tasks | Files |
|-------|-------|-------|
| **1. Critical Fixes** | Fix encoding in build, fix description cleaning, fix classification, deduplicate audit | `build_demo.py`, `fetch_descriptions.py`, `classification.py`, `classify_audit.py` |
| **2. Data Pipeline** | Fix fetch_episodes output schema, integrate thumbnail module, fix audit CSV completeness | `fetch_episodes.py`, `build_demo.py`, `channel_to_webapp.py`, `thumbnail.py` |
| **3. Template UX** | Theme modes, keyboard nav, a11y announcements, focus management | `daheeh-demo.html` |
| **4. Dashboard** | Import validation, export timestamp, profile gate | `daheeh-demo.html` |
| **5. Documentation** | Update CLAUDE.md, README.md, add workflow docs | `CLAUDE.md`, `README.md` |
| **6. Verification** | Dry-run build, audit report review, browser test checklist | All |

---

## 🎯 Acceptance Criteria for "Pro Service"

- [ ] Built HTML renders Arabic correctly in title, meta, and content
- [ ] Descriptions cleaned of promotional text, truncated at 500 chars
- [ ] >80% episodes classified with confidence ≥0.5
- [ ] Audit CSV has no duplicates, includes duration/thumbnail
- [ ] Theme toggle works: light/dark/system persisted in localStorage
- [ ] Keyboard navigation: `/` focuses search, arrows navigate chips, `Escape` clears
- [ ] Screen reader announces result count on filter/search
- [ ] Import validates schema + version, export includes timestamp
- [ ] Profile dialog: focus trap, Escape closes, focus returns
- [ ] Dry-run build passes without errors
- [ ] Browser test: mobile + desktop, RTL, light/dark, reduced motion, offline thumbnails