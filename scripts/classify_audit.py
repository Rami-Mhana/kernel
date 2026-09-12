#!/usr/bin/env python3
"""
============================================================
Classification Audit Script for dahih-archive
============================================================
Generates prioritized audit dataset for manual review:
- Low-confidence items
- Conflicting classifications
- Uncategorized items
- Missing descriptions
- Series boundary cases
- Deterministic sample seed for reproducibility
============================================================
"""
import csv
import random
import json
import re
from pathlib import Path
from dataclasses import dataclass
from typing import Optional
from collections import Counter

# Import shared modules
from content_schema import (
    Episode,
    AUDIT_CSV_FIELDS,
    clean_description_for_classification,
    load_manual_classifications,
)
from classification import (
    classify_deterministic,
    classify_episode_deterministic,
    get_taxonomy,
    load_taxonomy_config,
    AIProvider,
    TwoPassClassifier,
)


# ============ CONFIG ============
INPUT_CSV = Path("data/episodes_dahih_with_desc.csv")
OUTPUT_CSV = Path("data/episodes_classification_audit.csv")
RAW_DIR = Path("data/raw")
SAMPLE_SIZE = 100  # Increased from 50
SEED = 42

# Priority weights for audit sampling
PRIORITY_WEIGHTS = {
    "auto_low": 10,       # Low confidence - highest priority
    "conflict": 9,        # Conflicting proposals
    "auto_medium": 6,     # Medium confidence
    "pending": 5,         # Not yet classified
    "needs_review": 8,    # Flagged for review
    "auto_high": 2,       # High confidence - lower priority
    "manual": 1,          # Already reviewed - lowest priority (but include some for verification)
}


@dataclass
class AuditCandidate:
    """Candidate for audit with priority score."""
    episode: Episode
    priority_score: float
    priority_reasons: list[str]
    deterministic_result: Optional[object] = None  # ClassificationResult


def calculate_priority(ep: Episode, det_result) -> tuple[float, list[str]]:
    """Calculate audit priority score and reasons."""
    score = 0.0
    reasons = []

    # Base weight from audit status
    status_value = ep.audit_status.value if hasattr(ep.audit_status, "value") else ep.audit_status
    status_weight = PRIORITY_WEIGHTS.get(status_value, 1)
    score += status_weight
    if status_weight > 1:
        reasons.append(f"status:{status_value}")

    # Low confidence
    if ep.classification_confidence < 0.5:
        score += 5
        reasons.append("low_confidence")
    elif ep.classification_confidence < 0.7:
        score += 2
        reasons.append("medium_confidence")

    # Missing description
    if not ep.description or len(ep.description.strip()) < 50:
        score += 3
        reasons.append("missing_description")

    # Multiple proposed categories (conflict)
    if len(ep.proposed_categories) > 2:
        score += 4
        reasons.append("multiple_proposals")

    # "عام / متنوع" category (uncategorized)
    if ep.primary_category == "عام / متنوع":
        score += 3
        reasons.append("uncategorized")

    # Short content (Shorts) - often harder to classify
    if ep.content_type.value == "short":
        score += 2
        reasons.append("shorts")

    # Missing thumbnail
    if not ep.thumbnail_url:
        score += 1
        reasons.append("missing_thumbnail")

    # Series boundary - check if title suggests series but classification uncertain
    title_lower = ep.title.lower()
    series_indicators = ["جزء", "سلسلة", "حلقات", "part", "series", "episode"]
    if any(ind in title_lower for ind in series_indicators):
        score += 2
        reasons.append("series_boundary")

    # Deterministic vs AI disagreement (if both available)
    if det_result and ep.classification_model and "deterministic" not in ep.classification_model.lower():
        det_cat = det_result.primary_category
        ai_cat = ep.primary_category
        if det_cat != ai_cat:
            score += 6
            reasons.append("det_ai_disagreement")

    return score, reasons


def load_raw_metadata(raw_dir: Path) -> dict[str, dict]:
    """Load yt-dlp metadata keyed by video ID for CSVs with legacy schemas."""
    metadata = {}
    if not raw_dir.exists():
        return metadata
    for jsonl_path in raw_dir.glob("*.jsonl"):
        try:
            with jsonl_path.open(encoding="utf-8") as handle:
                for line in handle:
                    try:
                        record = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    video_id = record.get("id", "").strip()
                    if video_id:
                        metadata[video_id] = record
        except OSError as exc:
            print(f"[WARN] Could not read metadata cache {jsonl_path}: {exc}")
    return metadata


def video_id_from_url(url: str) -> str:
    match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", url or "")
    return match.group(1) if match else ""


def load_episodes_from_csv(csv_path: Path, raw_dir: Path = RAW_DIR) -> list[Episode]:
    """Load episodes from CSV file."""
    episodes = []
    if not csv_path.exists():
        print(f"[ERROR] Input CSV not found: {csv_path}")
        return episodes

    raw_metadata = load_raw_metadata(raw_dir)
    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            video_id = row.get("video_id", "").strip() or video_id_from_url(row.get("url", ""))
            raw = raw_metadata.get(video_id, {})
            # Legacy enrichment CSVs omit metadata that is available in yt-dlp
            # JSONL. Fill only missing values so curated CSV data remains authoritative.
            row["video_id"] = video_id
            row["duration_seconds"] = row.get("duration_seconds") or raw.get("duration") or 0
            row["duration_string"] = row.get("duration_string") or raw.get("duration_string") or ""
            row["thumbnail_url"] = row.get("thumbnail_url") or raw.get("thumbnail") or ""
            if not row["thumbnail_url"] and raw.get("thumbnails"):
                thumbnails = [item for item in raw["thumbnails"] if item.get("url")]
                if thumbnails:
                    row["thumbnail_url"] = thumbnails[-1]["url"]
            row["view_count"] = row.get("view_count") or raw.get("view_count") or 0
            # Convert pipe-separated fields back to lists
            for field in ["secondary_categories", "proposed_categories"]:
                if row.get(field):
                    row[field] = row[field].split("|") if row[field] else []
                else:
                    row[field] = []

            # Convert numeric fields
            for field in ["duration_seconds", "view_count"]:
                if row.get(field):
                    try:
                        row[field] = int(row[field])
                    except ValueError:
                        row[field] = 0
                else:
                    row[field] = 0

            if row.get("classification_confidence"):
                try:
                    row["classification_confidence"] = float(row["classification_confidence"])
                except ValueError:
                    row["classification_confidence"] = 0.0
            else:
                row["classification_confidence"] = 0.0

            episode = Episode.from_dict(row)
            if not episode.primary_category:
                result = classify_episode_deterministic(episode)
                episode.primary_category = result.primary_category
                episode.secondary_categories = result.secondary_categories
                episode.classification_confidence = result.confidence
                episode.classification_rationale = result.rationale
                episode.classification_model = result.model or "deterministic"
                episode.proposed_categories = [
                    f"{category}:{score}" for category, score in result.all_candidates
                ]
            episodes.append(episode)

    return episodes


def load_existing_audit(audit_path: Path) -> dict[str, dict]:
    """Load existing audit decisions to preserve manual corrections."""
    manual = {}
    if not audit_path.exists():
        return manual

    with open(audit_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            key = row.get("video_id", "").strip() or row.get("url", "").strip()
            if key:
                manual[key] = {
                    'manual_category': row.get('manual_category', '').strip(),
                    'manual_secondary': row.get('manual_secondary', '').strip(),
                    'manual_notes': row.get('manual_notes', '').strip(),
                    'audit_status': row.get('audit_status', '').strip(),
                }
    return manual


def run_deterministic_classification(episodes: list[Episode]) -> dict[str, object]:
    """Run deterministic classification on all episodes for comparison."""
    results = {}
    for ep in episodes:
        results[ep.video_id] = classify_episode_deterministic(ep)
    return results


def select_audit_sample(
    episodes: list[Episode],
    sample_size: int,
    seed: int = SEED,
    existing_audit: dict = None
) -> list[AuditCandidate]:
    """Select prioritized audit sample using weighted sampling."""
    if existing_audit is None:
        existing_audit = {}

    # Deduplicate episodes by video_id first
    unique_by_id = {}
    for ep in episodes:
        key = ep.video_id or ep.url
        current = unique_by_id.get(key)
        if current is None or episode_completeness(ep) > episode_completeness(current):
            unique_by_id[key] = ep
    unique_episodes = list(unique_by_id.values())

    print(f"  Deduplicated: {len(episodes)} -> {len(unique_episodes)} episodes")

    # Run deterministic classification for all
    print("  Running deterministic classification for priority calculation...")
    det_results = run_deterministic_classification(unique_episodes)

    # Calculate priority for each episode
    candidates = []
    for ep in unique_episodes:
        det_result = det_results.get(ep.video_id)
        score, reasons = calculate_priority(ep, det_result)

        # Boost score if already manually reviewed (for verification)
        audit_key = ep.video_id or ep.url
        if audit_key in existing_audit and existing_audit[audit_key].get('manual_category'):
            score += 0.5
            reasons.append("existing_review")

        candidates.append(AuditCandidate(
            episode=ep,
            priority_score=score,
            priority_reasons=reasons,
            deterministic_result=det_result
        ))

    # Sort by priority score (descending)
    candidates.sort(key=lambda c: c.priority_score, reverse=True)

    # Deterministic selection: take top N by priority score (no randomness for reproducibility)
    # This ensures same sample every run with same seed
    selected = candidates[:sample_size]

    return selected


def episode_completeness(ep: Episode) -> int:
    """Prefer the duplicate record with the most usable metadata."""
    return sum((
        bool(ep.title),
        bool(ep.url),
        bool(ep.channel),
        bool(ep.description),
        bool(ep.thumbnail_url),
        bool(ep.duration_seconds),
        bool(ep.duration_string),
        bool(ep.view_count),
        bool(ep.primary_category),
    ))


def generate_audit_csv(candidates: list[AuditCandidate], existing_audit: dict, output_path: Path) -> None:
    """Generate audit CSV with all required fields."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=AUDIT_CSV_FIELDS)
        writer.writeheader()

        for i, cand in enumerate(candidates, 1):
            ep = cand.episode
            det_result = cand.deterministic_result

            # Existing manual data
            manual = existing_audit.get(ep.video_id or ep.url, {})

            # Proposed categories
            proposed_primary = ep.primary_category
            proposed_secondary = "|".join(ep.secondary_categories) if ep.secondary_categories else ""
            all_proposed = "|".join(ep.proposed_categories) if ep.proposed_categories else proposed_primary

            # Deterministic result
            det_primary = det_result.primary_category if det_result else ""
            det_secondary = "|".join(det_result.secondary_categories) if det_result and det_result.secondary_categories else ""

            row = {
                "video_id": ep.video_id,
                "title": ep.title,
                "url": ep.url,
                "channel": ep.channel,
                "thumbnail_url": ep.thumbnail_url,
                "duration_string": ep.duration_string,
                "content_type": ep.content_type.value,
                "description": ep.description[:500] if ep.description else "",
                "refs_hint": ep.refs_hint,
                "proposed_primary": proposed_primary,
                "proposed_secondary": proposed_secondary,
                "all_proposed": all_proposed,
                "confidence": f"{ep.classification_confidence:.2f}",
                "rationale": ep.classification_rationale,
                "model": ep.classification_model,
                "classified_at": ep.classified_at,
                "det_primary": det_primary,
                "det_secondary": det_secondary,
                "det_confidence": f"{det_result.confidence:.2f}" if det_result else "",
                "manual_category": manual.get('manual_category', ''),
                "manual_secondary": manual.get('manual_secondary', ''),
                "manual_notes": manual.get('manual_notes', ''),
                "audit_status": manual.get(
                    "audit_status",
                    ep.audit_status.value if hasattr(ep.audit_status, "value") else ep.audit_status,
                ),
                "audit_timestamp": "",
                "priority_score": f"{cand.priority_score:.1f}",
                "priority_reasons": "|".join(cand.priority_reasons),
            }
            writer.writerow(row)

    print(f"[OK] Audit CSV written to {output_path}")
    print(f"   {len(candidates)} episodes selected for review")


def generate_quality_report(episodes: list[Episode], candidates: list[AuditCandidate], existing_audit: dict) -> None:
    """Generate quality report for the audit dataset."""
    print("\n[QUALITY REPORT]")

    # Category coverage
    cat_counts = Counter(ep.primary_category for ep in episodes)
    print(f"\n  Category distribution (all {len(episodes)} episodes):")
    for cat, count in cat_counts.most_common(15):
        cat_safe = cat.encode('ascii', 'replace').decode('ascii')
        pct = count / len(episodes) * 100
        print(f"    {cat_safe}: {count} ({pct:.1f}%)")

    # Audit status distribution
    status_counts = Counter(ep.audit_status for ep in episodes)
    print(f"\n  Audit status distribution:")
    for status, count in status_counts.most_common():
        status_safe = status.encode('ascii', 'replace').decode('ascii')
        pct = count / len(episodes) * 100
        print(f"    {status_safe}: {count} ({pct:.1f}%)")

    # Confidence distribution
    conf_buckets = {"<0.3": 0, "0.3-0.5": 0, "0.5-0.7": 0, "0.7-0.85": 0, "0.85+": 0}
    for ep in episodes:
        c = ep.classification_confidence
        if c < 0.3:
            conf_buckets["<0.3"] += 1
        elif c < 0.5:
            conf_buckets["0.3-0.5"] += 1
        elif c < 0.7:
            conf_buckets["0.5-0.7"] += 1
        elif c < 0.85:
            conf_buckets["0.7-0.85"] += 1
        else:
            conf_buckets["0.85+"] += 1
    print(f"\n  Confidence distribution:")
    for bucket, count in conf_buckets.items():
        pct = count / len(episodes) * 100
        print(f"    {bucket}: {count} ({pct:.1f}%)")

    # Content type distribution
    type_counts = Counter(ep.content_type.value for ep in episodes)
    print(f"\n  Content type distribution:")
    for ctype, count in type_counts.most_common():
        pct = count / len(episodes) * 100
        print(f"    {ctype}: {count} ({pct:.1f}%)")

    # Missing data
    missing_desc = sum(1 for ep in episodes if not ep.description or len(ep.description.strip()) < 50)
    missing_thumb = sum(1 for ep in episodes if not ep.thumbnail_url)
    print(f"\n  Data quality:")
    print(f"    Missing/short descriptions: {missing_desc} ({missing_desc/len(episodes)*100:.1f}%)")
    print(f"    Missing thumbnails: {missing_thumb} ({missing_thumb/len(episodes)*100:.1f}%)")

    # Selected sample stats
    print(f"\n  Selected audit sample ({len(candidates)} episodes):")
    sample_cats = Counter(c.episode.primary_category for c in candidates)
    for cat, count in sample_cats.most_common(10):
        cat_safe = cat.encode('ascii', 'replace').decode('ascii')
        print(f"    {cat_safe}: {count}")

    sample_status = Counter(c.episode.audit_status for c in candidates)
    for status, count in sample_status.most_common():
        status_safe = status.encode('ascii', 'replace').decode('ascii')
        print(f"    {status_safe}: {count}")

    avg_priority = sum(c.priority_score for c in candidates) / len(candidates) if candidates else 0
    print(f"    Average priority score: {avg_priority:.1f}")

    # Disagreement rate (if manual audit exists)
    if existing_audit:
        reviewed = [c for c in candidates if c.episode.url in existing_audit and existing_audit[c.episode.url].get('manual_category')]
        if reviewed:
            disagreements = sum(1 for c in reviewed if c.episode.primary_category != existing_audit[c.episode.url]['manual_category'])
            print(f"\n  Disagreement rate (vs existing manual): {disagreements}/{len(reviewed)} = {disagreements/len(reviewed)*100:.1f}%")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate prioritized classification audit dataset"
    )
    parser.add_argument("-i", "--input", default=str(INPUT_CSV), help="Input episodes CSV")
    parser.add_argument("-o", "--output", default=str(OUTPUT_CSV), help="Output audit CSV")
    parser.add_argument("-n", "--sample-size", type=int, default=SAMPLE_SIZE, help="Sample size")
    parser.add_argument("--seed", type=int, default=SEED, help="Random seed")
    parser.add_argument("--raw-dir", default=str(RAW_DIR), help="yt-dlp JSONL metadata directory")
    parser.add_argument("--taxonomy-config", help="Path to custom taxonomy JSON config")
    parser.add_argument("--report-only", action="store_true", help="Only generate quality report, no audit CSV")

    args = parser.parse_args()

    # Load taxonomy config
    if args.taxonomy_config:
        load_taxonomy_config(Path(args.taxonomy_config))

    print("=" * 60)
    print(f"[START] Classification Audit Generator")
    print(f"   Input:     {args.input}")
    print(f"   Output:    {args.output}")
    print(f"   Sample:    {args.sample_size}")
    print(f"   Seed:      {args.seed}")
    print("=" * 60)

    # Load episodes
    episodes = load_episodes_from_csv(Path(args.input), Path(args.raw_dir))
    if not episodes:
        print("[ERROR] No episodes loaded")
        sys.exit(1)

    print(f"[OK] Loaded {len(episodes)} episodes")

    # Load existing audit
    existing_audit = load_existing_audit(OUTPUT_CSV)
    print(f"[OK] Loaded {len(existing_audit)} existing audit records")

    # Select audit sample
    candidates = select_audit_sample(episodes, args.sample_size, args.seed, existing_audit)

    # Generate quality report
    generate_quality_report(episodes, candidates, existing_audit)

    if not args.report_only:
        # Generate audit CSV
        generate_audit_csv(candidates, existing_audit, Path(args.output))

        # Acceptance criteria
        print("\n[ACCEPTANCE CRITERIA]")
        low_conf = sum(1 for ep in episodes if ep.classification_confidence < 0.5)
        print(f"  Low confidence items (<0.5): {low_conf}")
        print(f"  Target: Review all low-confidence items before publish")
        print(f"  Target: >80% agreement on representative sample")

    print("\n[OK] Done!")


if __name__ == "__main__":
    import sys
    main()