#!/usr/bin/env python3
"""
============================================================
Shared Content Schema for dahih-archive
============================================================
Defines the canonical episode data structure used across all
pipeline stages: fetch, classify, audit, build.
Keyed by YouTube video_id for stability across rebuilds.
============================================================
"""
from __future__ import annotations
import json
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional
from enum import Enum


class ContentType(str, Enum):
    """YouTube content type classification."""
    VIDEO = "video"           # Long-form video (> 60s)
    SHORT = "short"           # YouTube Shorts (<= 60s, vertical)
    LIVE = "live"             # Live stream / past live
    UPCOMING = "upcoming"     # Scheduled premiere
    TRAILER = "trailer"       # Trailer/preview
    SUBSCRIBER_ONLY = "subscriber_only"  # Members-only content
    UNKNOWN = "unknown"


class AuditStatus(str, Enum):
    """Human audit status for classification."""
    PENDING = "pending"           # Not yet reviewed
    AUTO_HIGH = "auto_high"       # Auto-classified, high confidence
    AUTO_MEDIUM = "auto_medium"   # Auto-classified, medium confidence
    AUTO_LOW = "auto_low"         # Auto-classified, low confidence
    MANUAL = "manual"             # Human-reviewed and confirmed
    CONFLICT = "conflict"         # Multiple proposals disagreed
    NEEDS_REVIEW = "needs_review" # Flagged for human review


@dataclass
class Episode:
    """
    Canonical episode record.
    All pipeline stages read/write this structure.
    Video ID is the stable primary key.
    """
    # ============ REQUIRED (stable identity) ============
    video_id: str
    title: str
    url: str
    channel: str

    # ============ METADATA FROM yt-dlp ============
    duration_seconds: int = 0
    duration_string: str = ""
    view_count: int = 0
    publish_date: str = ""           # ISO 8601 if available, else empty
    playlist_id: str = ""            # Source playlist/series ID
    playlist_title: str = ""         # Source playlist/series title
    thumbnail_url: str = ""          # Best landscape thumbnail URL
    content_type: ContentType = ContentType.VIDEO
    availability: str = ""           # public, unlisted, private, subscriber_only
    live_status: str = ""            # is_live, was_live, not_live, post_live

    # ============ ENRICHMENT ============
    description: str = ""            # Cleaned, truncated (500 chars max)
    refs_hint: str = ""              # Extracted references from #: section

    # ============ CLASSIFICATION ============
    primary_category: str = ""       # Final category label
    secondary_categories: list[str] = field(default_factory=list)  # Additional tags
    classification_confidence: float = 0.0  # 0.0 - 1.0
    classification_rationale: str = ""      # Short explanation
    classification_model: str = ""          # Model/provider used
    classification_prompt_version: str = "" # Prompt version for reproducibility
    classified_at: str = ""                 # ISO timestamp

    # ============ AUDIT ============
    audit_status: AuditStatus = AuditStatus.PENDING
    audit_reviewer: str = ""
    audit_notes: str = ""
    audit_timestamp: str = ""
    proposed_categories: list[str] = field(default_factory=list)  # All candidates

    # ============ USER STATE (localStorage compatible) ============
    # These are NOT written to CSV/JSONL; they live in browser localStorage
    # Kept here for schema documentation only
    # user_watchlist: bool = False
    # user_status: str = ""          # "", "in-progress", "completed"
    # user_notes: str = ""
    # user_position_seconds: int = 0
    # user_updated_at: str = ""

    # ============ METHODS ============
    def to_dict(self) -> dict:
        """Convert to dict for JSON/CSV serialization."""
        d = asdict(self)
        # Convert enums to values
        d["content_type"] = self.content_type.value
        d["audit_status"] = self.audit_status.value
        # Convert list to pipe-separated string for CSV
        d["secondary_categories"] = "|".join(self.secondary_categories)
        d["proposed_categories"] = "|".join(self.proposed_categories)
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "Episode":
        """Create Episode from dict (JSON/CSV row)."""
        # Handle enum fields
        data = data.copy()
        if not data.get("video_id"):
            data["video_id"] = data.get("id", "")
        if not data["video_id"] and data.get("url"):
            match = re.search(r"(?:v=|youtu\.be/)([A-Za-z0-9_-]{11})", data["url"])
            data["video_id"] = match.group(1) if match else ""
        data["duration_string"] = data.get("duration_string", data.get("duration", "")) or ""
        data["thumbnail_url"] = data.get("thumbnail_url", data.get("thumbnail", "")) or ""
        if not data["thumbnail_url"] and data.get("video_id"):
            data["thumbnail_url"] = f"https://i.ytimg.com/vi/{data['video_id']}/hqdefault.jpg"
        data["primary_category"] = data.get("primary_category", data.get("category", data.get("domain", ""))) or ""
        data["audit_notes"] = data.get("audit_notes", data.get("notes", "")) or ""
        data["audit_status"] = data.get("audit_status", "pending") or "pending"
        if data.get("duration_seconds") and int(data["duration_seconds"]) <= 60:
            data["content_type"] = "short"
        valid_fields = set(cls.__dataclass_fields__)
        data = {key: value for key, value in data.items() if key in valid_fields}
        data["content_type"] = ContentType(data.get("content_type", "video"))
        data["audit_status"] = AuditStatus(data["audit_status"])
        # Handle pipe-separated lists
        if isinstance(data.get("secondary_categories"), str):
            data["secondary_categories"] = data["secondary_categories"].split("|") if data["secondary_categories"] else []
        if isinstance(data.get("proposed_categories"), str):
            data["proposed_categories"] = data["proposed_categories"].split("|") if data["proposed_categories"] else []
        return cls(**data)

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), ensure_ascii=False)

    @classmethod
    def from_json(cls, json_str: str) -> "Episode":
        """Deserialize from JSON string."""
        return cls.from_dict(json.loads(json_str))

    def get_stable_key(self) -> str:
        """Return the stable key for deduplication and user state."""
        return self.video_id

    def is_short(self) -> bool:
        """Check if content is a Short (<= 60 seconds)."""
        return self.content_type == ContentType.SHORT or (self.duration_seconds and self.duration_seconds <= 60)

    def is_long_form(self) -> bool:
        """Check if content is long-form (> 60 seconds)."""
        return self.content_type == ContentType.VIDEO and (not self.duration_seconds or self.duration_seconds > 60)


# ============ MANUAL CLASSIFICATIONS ============
def load_manual_classifications(audit_path: Optional[Path] = None) -> dict[str, dict]:
    """Load manual category decisions from an audit CSV."""
    if audit_path is None:
        audit_path = Path("data/episodes_classification_audit.csv")
    if not audit_path.exists():
        return {}
    manual = {}
    import csv
    with open(audit_path, encoding="utf-8-sig") as handle:
        for row in csv.DictReader(handle):
            video_id = row.get("video_id", "").strip()
            url = row.get("url", "").strip()
            key = video_id or url
            if key and (row.get("manual_category", "").strip() or row.get("manual_notes", "").strip()):
                manual[key] = row
    return manual


# ============ CSV FIELD NAMES ============
# Used for consistent CSV column ordering across pipeline stages
EPISODE_CSV_FIELDS = [
    "video_id",
    "title",
    "url",
    "channel",
    "duration_seconds",
    "duration_string",
    "view_count",
    "publish_date",
    "playlist_id",
    "playlist_title",
    "thumbnail_url",
    "content_type",
    "availability",
    "live_status",
    "description",
    "refs_hint",
    "primary_category",
    "secondary_categories",
    "classification_confidence",
    "classification_rationale",
    "classification_model",
    "classification_prompt_version",
    "classified_at",
    "audit_status",
    "audit_reviewer",
    "audit_notes",
    "audit_timestamp",
    "proposed_categories",
]


# ============ AUDIT CSV FIELD NAMES ============
AUDIT_CSV_FIELDS = [
    "video_id",
    "title",
    "url",
    "channel",
    "thumbnail_url",
    "duration_string",
    "content_type",
    "description",
    "refs_hint",
    "proposed_primary",
    "proposed_secondary",
    "all_proposed",
    "confidence",
    "rationale",
    "model",
    "classified_at",
    "manual_category",
    "manual_secondary",
    "manual_notes",
    "audit_status",
    "audit_timestamp",
    "det_primary",
    "det_secondary",
    "det_confidence",
    "priority_score",
    "priority_reasons",
]


def create_episode_from_yt_dlp(data: dict, channel_label: str) -> Episode:
    """
    Create Episode from raw yt-dlp JSONL record.
    This is the single canonical parser for raw metadata.
    """
    vid = data.get("id", "")
    duration = data.get("duration", 0) or 0
    thumbnails = data.get("thumbnails") or []

    # Determine content type
    content_type = ContentType.VIDEO
    if duration and duration <= 60:
        content_type = ContentType.SHORT
    elif data.get("live_status") in ("is_live", "was_live", "post_live"):
        content_type = ContentType.LIVE
    elif data.get("availability") == "subscriber_only":
        content_type = ContentType.SUBSCRIBER_ONLY

    # Select best thumbnail (landscape preferred)
    landscape = [t for t in thumbnails if t.get("width", 0) >= t.get("height", 0)]
    candidates = landscape or thumbnails
    thumbnail_url = ""
    if candidates and candidates[-1].get("url"):
        thumbnail_url = candidates[-1]["url"]
    elif vid:
        thumbnail_url = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"

    # Extract playlist/series info
    playlist_id = data.get("playlist_id", "") or ""
    playlist_title = data.get("playlist_title", "") or ""

    # Publish date (epoch -> ISO)
    publish_date = ""
    ts = data.get("timestamp") or data.get("epoch")
    if ts:
        try:
            publish_date = datetime.fromtimestamp(int(ts)).isoformat()
        except (ValueError, TypeError):
            pass

    return Episode(
        video_id=vid,
        title=data.get("title", "").strip(),
        url=f"https://www.youtube.com/watch?v={vid}",
        channel=channel_label,
        duration_seconds=duration,
        duration_string=data.get("duration_string", "") or "",
        view_count=data.get("view_count", 0) or 0,
        publish_date=publish_date,
        playlist_id=playlist_id,
        playlist_title=playlist_title,
        thumbnail_url=thumbnail_url,
        content_type=content_type,
        availability=data.get("availability", "") or "",
        live_status=data.get("live_status", "") or "",
    )


def normalize_arabic_text(text: str) -> str:
    """
    Normalize Arabic text for consistent classification.
    - Remove diacritics (tashkeel)
    - Normalize alef variants
    - Normalize ta marbuta
    - Remove tatweel (kashida)
    - Collapse whitespace
    """
    if not text:
        return ""

    # Remove diacritics (tashkeel)
    import re
    text = re.sub(r'[ً-ٰٟۖ-ۭ]', '', text)

    # Normalize alef variants
    text = text.replace('آ', 'ا')  # آ -> ا
    text = text.replace('أ', 'ا')  # أ -> ا
    text = text.replace('إ', 'ا')  # إ -> ا
    text = text.replace('ٱ', 'ا')  # ا -> ا (alef wasla)

    # Normalize ta marbuta
    text = text.replace('ة', 'ه')  # ة -> ه

    # Remove tatweel (kashida)
    text = text.replace('ـ', '')

    # Normalize ya variants
    text = text.replace('ى', 'ي')  # ى -> ي

    # Collapse whitespace
    text = re.sub(r'\s+', ' ', text).strip()

    return text


def clean_description_for_classification(description: str) -> str:
    """
    Remove promotional and reference boilerplate while preserving topical prose.

    YouTube descriptions for this channel commonly contain a short introduction
    followed by a ``#:`` references section. Reference entries are useful for
    provenance, but URLs and citation titles are poor classification input.
    """
    if not description:
        return ""

    import re

    text = description.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    # Keep the editorial introduction and discard the citation block.
    text = re.split(
        r"(?i)(?:#\s*:|(?:المصادر|المراجع|references?)\s*:)",
        text,
        maxsplit=1,
    )[0]
    lines = text.split("\n")
    cleaned_lines = []

    # Patterns to skip when a line is entirely boilerplate.
    skip_patterns = [
        r"^\s*(?:https?://|www\.)",
        r"^\s*[:#@.\-_\s]*(?:[@#]\w+)(?:\s+[@#]\w+)*\s*$",
        r"(اشترك|subscribe|follow|تابع|لا تنس|don't forget)",
        r"(رابط|link|لينك).{0,80}(https?://|www\.)",
        r"(كود|كوبون|خصم|discount|promo(?:tion)?|sponsor(?:ed)?|code)",
        r"(دعم|donate|patreon|buy me a coffee)",
        r'^[\s\-_=*•·]{3,}$',    # Separator lines
    ]
    skip_regex = [re.compile(p, re.IGNORECASE) for p in skip_patterns]
    url_regex = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)

    for line in lines:
        line = re.sub(r"[ \t]+", " ", line).strip()
        if not line:
            continue
        if any(rx.search(line) for rx in skip_regex):
            continue
        # Drop citation-only fragments that were not under an explicit marker.
        without_urls = url_regex.sub("", line).strip(" -:|,؛،")
        if not without_urls or len(url_regex.findall(line)) >= 2 and len(without_urls) < 30:
            continue
        # YouTube metadata sometimes contains replacement characters and
        # punctuation-only remnants around an otherwise empty reference block.
        if "\ufffd" in without_urls:
            without_urls = without_urls.replace("\ufffd", " ")
        if not re.search(r"[A-Za-z\u0600-\u06ff\u0750-\u077f0-9]", without_urls):
            continue
        cleaned_lines.append(without_urls)

    return re.sub(r"\s+", " ", " ".join(cleaned_lines)).strip()


def deduplicate_episodes(episodes: list[Episode]) -> list[Episode]:
    """
    Deduplicate episodes by video_id, keeping the most complete record.
    """
    seen: dict[str, Episode] = {}
    for ep in episodes:
        key = ep.video_id
        if key not in seen:
            seen[key] = ep
        else:
            # Keep the one with more complete data (has description, category, etc.)
            existing = seen[key]
            new_score = _completeness_score(ep)
            old_score = _completeness_score(existing)
            if new_score > old_score:
                seen[key] = ep
    return list(seen.values())


def _completeness_score(ep: Episode) -> int:
    """Score episode completeness for deduplication."""
    score = 0
    if ep.description: score += 10
    if ep.primary_category: score += 5
    if ep.thumbnail_url: score += 3
    if ep.duration_seconds: score += 2
    if ep.view_count: score += 1
    if ep.publish_date: score += 1
    return score