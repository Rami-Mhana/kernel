#!/usr/bin/env python3
"""
============================================================
YouTube Channel → Educational Web App Pipeline
============================================================
Sellable service for Khamsat: "أحول قناتك يوتيوب إلى مكتبة تعليمية مصنفة"

Usage:
    python scripts/channel_to_webapp.py "https://www.youtube.com/@CHANNEL_NAME/videos" --output mychannel-demo.html
    python scripts/channel_to_webapp.py "https://www.youtube.com/playlist?list=PLAYLIST_ID" --output myplaylist-demo.html

Output: Single HTML file (no framework, no backend, works offline)
============================================================
"""
import argparse
import csv
import html
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

# Fix Windows console encoding so Arabic text and Unicode glyphs (e.g. →)
# can be printed without UnicodeEncodeError.
if sys.platform == "win32":
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding="utf-8")
        except Exception:
            pass

# Import shared modules
from content_schema import (
    Episode,
    ContentType,
    AuditStatus,
    create_episode_from_yt_dlp,
    EPISODE_CSV_FIELDS,
    normalize_arabic_text,
    clean_description_for_classification,
    deduplicate_episodes,
)
from classification import (
    TwoPassClassifier,
    AIProvider,
    classify_episode_deterministic,
    load_taxonomy_config,
    get_taxonomy,
)
from thumbnail import select_best_thumbnail, get_thumbnail_for_content_type


# ============ CONFIG ============
TEMPLATE_PATH = Path(__file__).parent.parent / "daheeh-demo.html"
DEFAULT_SLEEP = 1.5  # seconds between yt-dlp calls (rate limiting)
MAX_DESC_LENGTH = 500


# ============ HELPERS ============
def run_cmd(cmd: list[str], cwd: Optional[Path] = None, capture: bool = True) -> subprocess.CompletedProcess:
    """Run command with proper encoding handling."""
    result = subprocess.run(cmd, cwd=cwd, capture_output=capture, text=False)
    if capture:
        stdout = result.stdout.decode('utf-8', errors='replace') if result.stdout else ''
        stderr = result.stderr.decode('utf-8', errors='replace') if result.stderr else ''
        return subprocess.CompletedProcess(result.args, result.returncode, stdout, stderr)
    return result


def slugify(text: str) -> str:
    """Create filesystem-safe slug from channel name."""
    text = re.sub(r'[^\w\s-]', '', text, flags=re.UNICODE)
    text = re.sub(r'[\s-]+', '-', text.strip())
    return text.lower()[:50]


def extract_video_id(url: str) -> Optional[str]:
    """Extract YouTube video ID from URL."""
    patterns = [
        r'(?:v=|/)([a-zA-Z0-9_-]{11})(?:\?|&|$)',
        r'youtu\.be/([a-zA-Z0-9_-]{11})',
        r'embed/([a-zA-Z0-9_-]{11})',
    ]
    for pat in patterns:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    return None


# ============ STEP 1: FETCH VIDEOS ============
def fetch_channel_videos(channel_url: str, raw_dir: Path, channel_slug: str) -> Path:
    """Use yt-dlp to fetch all videos from channel/playlist as JSONL."""
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_path = raw_dir / f"{channel_slug}.jsonl"

    print(f"[1/5] Fetching videos from: {channel_url}")
    cmd = ["yt-dlp", "--flat-playlist", "--dump-json", channel_url]

    result = run_cmd(cmd)
    if result.returncode != 0:
        stderr_safe = result.stderr[:300].encode('ascii', 'replace').decode('ascii')
        print(f"  [WARN] yt-dlp warning: {stderr_safe}")
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(result.stdout)

    # Count videos
    count = sum(1 for _ in open(output_path, encoding="utf-8") if _.strip())
    print(f"  [OK] Found {count} videos -> {output_path}")
    return output_path


# ============ STEP 2: PARSE JSONL ============
def parse_jsonl(jsonl_path: Path, channel_label: str) -> list[Episode]:
    """Parse yt-dlp JSONL into Episode objects using shared schema."""
    episodes = []
    with open(jsonl_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            vid = data.get('id')
            if not vid:
                continue

            # Use shared parser for canonical Episode creation
            episode = create_episode_from_yt_dlp(data, channel_label)
            episodes.append(episode)

    return episodes


# ============ STEP 3: FETCH DESCRIPTIONS ============
def fetch_description(video_url: str) -> str:
    """Fetch video description using yt-dlp."""
    cmd = ["yt-dlp", "--skip-download", "--print", "%(description)s", video_url]
    result = run_cmd(cmd, capture=True)
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def enrich_episodes(
    episodes: list[Episode],
    sleep_seconds: float,
    classifier: Optional[TwoPassClassifier] = None
) -> list[Episode]:
    """Fetch descriptions for all episodes with rate limiting and classification."""
    print(f"[3/5] Fetching descriptions and classifying {len(episodes)} videos...")
    enriched = []

    for i, ep in enumerate(episodes, 1):
        desc = fetch_description(ep.url)

        # Clean and truncate description
        desc_clean = clean_description_for_classification(desc)
        desc_clean = desc_clean.replace("\n", " ").strip()[:MAX_DESC_LENGTH]

        # Extract references hint (after #:)
        refs_hint = ""
        if "#:" in desc:
            refs_hint = desc.split("#:")[-1].strip()[:300]
        elif "# :" in desc:
            refs_hint = desc.split("# :")[-1].strip()[:300]

        # Update episode with description
        ep.description = desc_clean
        ep.refs_hint = refs_hint

        # Classify if classifier provided
        if classifier:
            classifier.classify(ep)
        else:
            # Fallback to deterministic only
            result = classify_episode_deterministic(ep)
            ep.primary_category = result.primary_category
            ep.secondary_categories = result.secondary_categories
            ep.classification_confidence = result.confidence
            ep.classification_rationale = result.rationale
            ep.classification_model = result.model
            ep.classification_prompt_version = result.prompt_version
            ep.classified_at = time.strftime("%Y-%m-%dT%H:%M:%S")
            # all_candidates is list[(category, score)] tuples; proposed_categories is
            # list[str] and gets "|".join()'d in Episode.to_dict(), so store as strings.
            ep.proposed_categories = [f"{cat}:{score}" for cat, score in result.all_candidates]
            if result.confidence >= 0.8:
                ep.audit_status = AuditStatus.AUTO_HIGH
            elif result.confidence >= 0.5:
                ep.audit_status = AuditStatus.AUTO_MEDIUM
            else:
                ep.audit_status = AuditStatus.AUTO_LOW

        enriched.append(ep)

        # Progress
        if i % 10 == 0 or i == len(episodes):
            cat = ep.primary_category or "غير مصنف"
            conf = ep.classification_confidence
            print(f"  [{i}/{len(episodes)}] {ep.title[:50]}... → {cat} ({conf:.0%})")

        if i < len(episodes):
            time.sleep(sleep_seconds)

    return enriched


# ============ STEP 4: SAVE CSV ============
def save_episodes_csv(episodes: list[Episode], output_path: Path) -> None:
    """Save episodes to CSV with full schema."""
    print(f"[4/5] Saving CSV → {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=EPISODE_CSV_FIELDS)
        writer.writeheader()
        for ep in episodes:
            writer.writerow(ep.to_dict())

    print(f"  [OK] Saved {len(episodes)} episodes")


# ============ STEP 5: BUILD HTML ============
def build_html(episodes: list[Episode], channel_name: str, output_path: Path) -> None:
    """Inject episodes into HTML template and write output."""
    print(f"[5/5] Building HTML demo → {output_path}")

    # Read template
    with open(TEMPLATE_PATH, encoding="utf-8") as f:
        template = f.read()

    # Update title/meta for this channel
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
    data_json = json.dumps(episodes_data, ensure_ascii=False, separators=(',', ':'))
    # Escape for safe JS injection
    data_json = data_json.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    output_html = template.replace(
        'const EPISODES_DATA = [\n  // Data will be injected here by the build script\n];',
        f'const EPISODES_DATA = {data_json};'
    )

    # Write
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(output_html)

    print(f"  [OK] Done! Open {output_path} in browser")


# ============ MAIN PIPELINE ============
def main():
    parser = argparse.ArgumentParser(
        description="YouTube Channel -> Educational Web App (single HTML file)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # From channel videos page
  python channel_to_webapp.py "https://www.youtube.com/@AJpluskibreet/videos" -o aj_kabrit.html

  # From playlist
  python channel_to_webapp.py "https://www.youtube.com/playlist?list=PLxxx" -o playlist.html

  # With AI classification (requires API key)
  python channel_to_webapp.py "URL" -o out.html --ai-provider anthropic --ai-api-key $ANTHROPIC_API_KEY

  # Custom sleep (faster/slower)
  python channel_to_webapp.py "URL" -o out.html --sleep 2.0

  # Skip description fetching (faster, less data)
  python channel_to_webapp.py "URL" -o out.html --skip-descriptions

  # Load custom taxonomy config
  python channel_to_webapp.py "URL" -o out.html --taxonomy-config config/my_taxonomy.json
        """
    )
    parser.add_argument("url", help="YouTube channel URL (/videos) or playlist URL")
    parser.add_argument("-o", "--output", required=True, help="Output HTML file path")
    parser.add_argument("--name", help="Display name for the generated library")
    parser.add_argument("--sleep", type=float, default=DEFAULT_SLEEP, help="Seconds between description fetches (default: 1.5)")
    parser.add_argument("--skip-descriptions", action="store_true", help="Skip description fetching (faster, less data)")
    parser.add_argument("--raw-dir", default="data/raw", help="Directory for raw JSONL cache")
    parser.add_argument("--csv-output", help="Optional CSV output path (default: data/episodes_<slug>.csv)")

    # AI Classification options
    parser.add_argument("--ai-provider", choices=["none", "openai", "anthropic", "google"], default="none",
                        help="AI provider for classification (default: none)")
    parser.add_argument("--ai-api-key", help="API key for AI provider (or set env var)")
    parser.add_argument("--ai-model", help="Model name for AI provider")
    parser.add_argument("--confidence-threshold", type=float, default=0.7,
                        help="Confidence threshold for AI fallback (default: 0.7)")

    # Taxonomy config
    parser.add_argument("--taxonomy-config", help="Path to custom taxonomy JSON config")

    args = parser.parse_args()

    # Validate URL
    if "youtube.com" not in args.url and "youtu.be" not in args.url:
        print("[ERROR] Error: Must be a YouTube URL", file=sys.stderr)
        sys.exit(1)

    # Load taxonomy config if provided
    if args.taxonomy_config:
        load_taxonomy_config(Path(args.taxonomy_config))

    # Derive channel slug from URL
    channel_slug = slugify(args.name or args.url)
    channel_label = args.name.strip() if args.name else channel_slug.replace('-', ' ').title()

    # Paths
    raw_dir = Path(args.raw_dir)
    raw_dir.mkdir(parents=True, exist_ok=True)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # CSV output path
    if args.csv_output:
        csv_output = Path(args.csv_output)
    else:
        csv_output = Path("data") / f"episodes_{channel_slug}.csv"

    print("=" * 60)
    print(f"[START] Channel -> Web App Pipeline")
    print(f"   Channel: {args.url}")
    print(f"   Label:   {channel_label}")
    print(f"   Output:  {output_path}")
    print(f"   CSV:     {csv_output}")
    if args.ai_provider != "none":
        print(f"   AI:      {args.ai_provider} ({args.ai_model or 'default'})")
    print("=" * 60)

    try:
        # Step 1: Fetch videos
        jsonl_path = fetch_channel_videos(args.url, raw_dir, channel_slug)

        # Step 2: Parse
        print("[2/5] Parsing video metadata...")
        episodes = parse_jsonl(jsonl_path, channel_label)
        print(f"  [OK] Parsed {len(episodes)} episodes")

        # Deduplicate by video_id
        episodes = deduplicate_episodes(episodes)
        print(f"  [OK] After deduplication: {len(episodes)} episodes")

        # Step 3: Enrich (optional)
        classifier = None
        if not args.skip_descriptions:
            # Setup AI classifier if requested
            if args.ai_provider != "none":
                ai_key = args.ai_api_key or os.environ.get(f"{args.ai_provider.upper()}_API_KEY")
                if ai_key:
                    provider_enum = AIProvider(args.ai_provider)
                    classifier = TwoPassClassifier(
                        ai_provider=provider_enum,
                        ai_api_key=ai_key,
                        ai_model=args.ai_model or "",
                        confidence_threshold=args.confidence_threshold
                    )
                    print(f"  [AI] Classifier initialized: {provider_enum.value}")
                else:
                    print(f"  [WARN] AI provider {args.ai_provider} requested but no API key found")

            episodes = enrich_episodes(episodes, args.sleep, classifier)
        else:
            print("[3/5] Skipping description fetch (--skip-descriptions)")
            for ep in episodes:
                ep.primary_category = "عام / متنوع"
                ep.audit_status = AuditStatus.PENDING

        # Step 4: Save CSV
        save_episodes_csv(episodes, csv_output)

        # Step 5: Build HTML
        build_html(episodes, channel_label, output_path)

        # Summary
        from collections import Counter
        cat_counts = Counter(ep.primary_category for ep in episodes)
        conf_counts = Counter(ep.audit_status.value for ep in episodes)
        content_type_counts = Counter(ep.content_type.value for ep in episodes)

        print("\n[SUMMARY]")
        print(f"   Total episodes: {len(episodes)}")
        print(f"   Categories: {len(cat_counts)}")
        for cat, count in cat_counts.most_common(10):
            cat_safe = cat.encode('ascii', 'replace').decode('ascii')
            print(f"     {cat_safe}: {count}")
        print(f"   Content types: {dict(content_type_counts)}")
        print(f"   Audit statuses: {dict(conf_counts)}")

        print(f"\n[OK] Success! Deliverable: {args.output}")
        print("   -> Single HTML file, works offline, no dependencies")
        print("   -> Ready to send to client or host on GitHub Pages/Netlify")

    except KeyboardInterrupt:
        print("\n[WARN] Interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()