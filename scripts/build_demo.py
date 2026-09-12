#!/usr/bin/env python3
"""
============================================================
Build script: Inject episode data into the standalone HTML demo.
============================================================
Reads processed episodes CSV + classification audit overrides,
outputs daheeh-demo-built.html (or custom output).
============================================================
"""
import csv
import json
import html
import argparse
from pathlib import Path
from typing import Optional

# Import shared modules
from content_schema import Episode, EPISODE_CSV_FIELDS
from classification import classify_episode_deterministic
from content_schema import clean_description_for_classification


# ============ CONFIG ============
DEFAULT_EPISODES_CSV = Path("data/episodes_dahih_with_desc.csv")
DEFAULT_AUDIT_CSV = Path("data/episodes_classification_audit.csv")
DEFAULT_TEMPLATE_HTML = Path("daheeh-demo.html")
DEFAULT_OUTPUT_HTML = Path("daheeh-demo-built.html")


def load_manual_classifications(audit_path: Path) -> dict[str, dict]:
    """Load manual corrections from audit CSV."""
    manual = {}
    if not audit_path.exists():
        print(f"[WARN] Audit CSV not found: {audit_path}")
        return manual

    with open(audit_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            url = row.get('url', '').strip()
            if not url:
                continue

            manual_category = row.get('manual_category', '').strip()
            manual_secondary = row.get('manual_secondary', '').strip()
            manual_notes = row.get('manual_notes', '').strip()
            audit_status = row.get('audit_status', '').strip()

            if manual_category or manual_secondary or manual_notes:
                manual[url] = {
                    'primary': manual_category,
                    'secondary': manual_secondary,
                    'notes': manual_notes,
                    'status': audit_status or 'manual'
                }

    print(f"[OK] Loaded {len(manual)} manual classifications from audit")
    return manual


def load_episodes(csv_path: Path) -> list[Episode]:
    """Load episodes from CSV using shared schema."""
    episodes = []
    if not csv_path.exists():
        print(f"[ERROR] Episodes CSV not found: {csv_path}")
        return episodes

    with open(csv_path, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
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


def apply_manual_overrides(episodes: list[Episode], manual: dict[str, dict]) -> list[Episode]:
    """Apply manual audit overrides to episodes."""
    overridden = 0
    for ep in episodes:
        if ep.url in manual:
            override = manual[ep.url]
            if override['primary']:
                ep.primary_category = override['primary']
                ep.audit_status = override['status'] or 'manual'
            if override['secondary']:
                ep.secondary_categories = [s.strip() for s in override['secondary'].split('|') if s.strip()]
            overridden += 1
    print(f"[OK] Applied {overridden} manual overrides")
    return episodes


def build_html(episodes: list[Episode], template_path: Path, output_path: Path, channel_name: str = "دحيح بيديا") -> None:
    """Inject episodes into HTML template and write output."""
    print(f"[BUILD] Reading template: {template_path}")

    if not template_path.exists():
        print(f"[ERROR] Template not found: {template_path}")
        return

    with open(template_path, encoding="utf-8") as f:
        template = f.read()

    # Update title/meta - use Arabic text directly (template is UTF-8)
    safe_channel_name = html.escape(channel_name, quote=True)
    template = template.replace(
        "دحيح بيديا — أرشيف حلقات الدحيح مصنفة",
        f"{safe_channel_name} — مكتبة فيديوهات تعليمية مصنفة"
    )
    template = template.replace(
        '<strong id="channelName">القناة</strong>',
        f'<strong id="channelName">{safe_channel_name}</strong>'
    )

    # Convert episodes to JSON-serializable dicts
    episodes_data = [ep.to_dict() for ep in episodes]
    # JSON with ensure_ascii=False preserves Arabic; escape only </script> and HTML-breaking sequences
    data_json = json.dumps(episodes_data, ensure_ascii=False, separators=(',', ':'))
    # Escape for safe JS injection inside <script> tag - only </script> and </style> are dangerous
    data_json = data_json.replace("</script>", "<\\/script>").replace("</style>", "<\\/style>")
    output_html = template.replace(
        'const EPISODES_DATA = [\n  // Data will be injected here by the build script\n];',
        f'const EPISODES_DATA = {data_json};'
    )

    # Write output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(output_html)

    print(f"[OK] Built {output_path}")


def print_statistics(episodes: list[Episode]) -> None:
    """Print category and quality statistics."""
    from collections import Counter

    cat_counts = Counter(ep.primary_category for ep in episodes)
    status_counts = Counter(ep.audit_status for ep in episodes)
    type_counts = Counter(ep.content_type.value for ep in episodes)
    channel_counts = Counter(ep.channel for ep in episodes)

    print(f"\n[STATS] Total episodes: {len(episodes)}")
    print(f"  Channels: {len(channel_counts)}")
    for ch, cnt in channel_counts.most_common():
        print(f"    {ch}: {cnt}")

    print(f"\n  Categories ({len(cat_counts)}):")
    for cat, count in cat_counts.most_common():
        cat_safe = cat.encode('ascii', 'replace').decode('ascii')
        print(f"    {cat_safe}: {count}")

    print(f"\n  Audit statuses:")
    for status, count in status_counts.most_common():
        status_safe = status.encode('ascii', 'replace').decode('ascii')
        print(f"    {status_safe}: {count}")

    print(f"\n  Content types:")
    for ctype, count in type_counts.most_common():
        print(f"    {ctype}: {count}")

    # Confidence stats
    confidences = [ep.classification_confidence for ep in episodes if ep.classification_confidence > 0]
    if confidences:
        avg_conf = sum(confidences) / len(confidences)
        low_conf = sum(1 for c in confidences if c < 0.5)
        print(f"\n  Classification confidence:")
        print(f"    Average: {avg_conf:.2f}")
        print(f"    Low (<0.5): {low_conf} ({low_conf/len(confidences)*100:.1f}%)")


def main():
    parser = argparse.ArgumentParser(
        description="Build standalone HTML demo from episodes CSV and audit overrides"
    )
    parser.add_argument("-i", "--episodes", default=str(DEFAULT_EPISODES_CSV),
                        help=f"Input episodes CSV (default: {DEFAULT_EPISODES_CSV})")
    parser.add_argument("-a", "--audit", default=str(DEFAULT_AUDIT_CSV),
                        help=f"Audit CSV with manual overrides (default: {DEFAULT_AUDIT_CSV})")
    parser.add_argument("-t", "--template", default=str(DEFAULT_TEMPLATE_HTML),
                        help=f"HTML template (default: {DEFAULT_TEMPLATE_HTML})")
    parser.add_argument("-o", "--output", default=str(DEFAULT_OUTPUT_HTML),
                        help=f"Output HTML file (default: {DEFAULT_OUTPUT_HTML})")
    parser.add_argument("--name", default="دحيح بيديا", help="Library display name")
    parser.add_argument("--stats-only", action="store_true", help="Only print statistics, don't build HTML")

    args = parser.parse_args()

    print("=" * 60)
    print(f"[START] Build Demo")
    print(f"   Episodes: {args.episodes}")
    print(f"   Audit:    {args.audit}")
    print(f"   Template: {args.template}")
    print(f"   Output:   {args.output}")
    print(f"   Name:     {args.name}")
    print("=" * 60)

    # Load data
    episodes = load_episodes(Path(args.episodes))
    if not episodes:
        print("[ERROR] No episodes loaded")
        return

    # Apply manual overrides
    manual = load_manual_classifications(Path(args.audit))
    episodes = apply_manual_overrides(episodes, manual)

    # Print statistics
    print_statistics(episodes)

    if not args.stats_only:
        # Build HTML
        build_html(episodes, Path(args.template), Path(args.output), args.name)

    print("\n[OK] Done!")


if __name__ == "__main__":
    main()