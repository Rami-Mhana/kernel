#!/usr/bin/env python3
"""
============================================================
Shared Thumbnail Module for dahih-archive
============================================================
Selects best usable thumbnail from yt-dlp metadata with
predictable fallback URL based on video ID.
============================================================
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional
from enum import Enum


class ThumbnailQuality(str, Enum):
    """YouTube thumbnail quality levels."""
    MAXRES = "maxresdefault"      # 1280x720 (not always available)
    HIGH = "hqdefault"            # 480x360 (always available)
    MEDIUM = "mqdefault"          # 320x180
    STANDARD = "sddefault"        # 640x480 (not always available)
    DEFAULT = "default"           # 120x90


@dataclass
class ThumbnailInfo:
    """Thumbnail metadata from yt-dlp."""
    url: str
    width: int = 0
    height: int = 0
    quality: ThumbnailQuality = ThumbnailQuality.DEFAULT


# YouTube thumbnail URL patterns
YT_THUMB_BASE = "https://i.ytimg.com/vi/{video_id}/{quality}.jpg"
YT_THUMB_BASE_WEBP = "https://i.ytimg.com/vi/{video_id}/{quality}.webp"

# Quality preference order (best first)
QUALITY_PREFERENCE = [
    ThumbnailQuality.MAXRES,
    ThumbnailQuality.HIGH,
    ThumbnailQuality.STANDARD,
    ThumbnailQuality.MEDIUM,
    ThumbnailQuality.DEFAULT,
]

# Aspect ratio thresholds
LANDSCAPE_MIN_RATIO = 1.33  # 4:3 or wider
PORTRAIT_MAX_RATIO = 0.75   # 3:4 or taller
SQUARE_RATIO_RANGE = (0.9, 1.1)


def parse_yt_dlp_thumbnails(thumbnails: list[dict]) -> list[ThumbnailInfo]:
    """
    Parse yt-dlp thumbnail list into structured ThumbnailInfo objects.
    """
    result = []
    for t in thumbnails or []:
        url = t.get("url", "")
        if not url:
            continue
        width = t.get("width", 0) or 0
        height = t.get("height", 0) or 0
        # Try to infer quality from URL
        quality = ThumbnailQuality.DEFAULT
        for q in ThumbnailQuality:
            if q.value in url:
                quality = q
                break
        result.append(ThumbnailInfo(url=url, width=width, height=height, quality=quality))
    return result


def is_landscape(thumb: ThumbnailInfo) -> bool:
    """Check if thumbnail is landscape (width >= height * 1.33)."""
    if thumb.width <= 0 or thumb.height <= 0:
        return False
    return thumb.width / thumb.height >= LANDSCAPE_MIN_RATIO


def is_portrait(thumb: ThumbnailInfo) -> bool:
    """Check if thumbnail is portrait (height >= width * 1.33)."""
    if thumb.width <= 0 or thumb.height <= 0:
        return False
    return thumb.height / thumb.width >= LANDSCAPE_MIN_RATIO


def is_square(thumb: ThumbnailInfo) -> bool:
    """Check if thumbnail is roughly square."""
    if thumb.width <= 0 or thumb.height <= 0:
        return False
    ratio = thumb.width / thumb.height
    return SQUARE_RATIO_RANGE[0] <= ratio <= SQUARE_RATIO_RANGE[1]


def select_best_thumbnail(
    thumbnails: list[dict],
    video_id: str,
    prefer_landscape: bool = True,
    allow_fallback: bool = True
) -> str:
    """
    Select the best thumbnail from yt-dlp metadata.

    Priority:
    1. Landscape thumbnails from yt-dlp (highest quality first)
    2. Any thumbnail from yt-dlp (highest quality first)
    3. Predictable fallback URL based on video_id

    Args:
        thumbnails: Raw thumbnail list from yt-dlp
        video_id: YouTube video ID for fallback
        prefer_landscape: If True, prefer landscape orientation
        allow_fallback: If True, use generated fallback URL

    Returns:
        Best available thumbnail URL
    """
    parsed = parse_yt_dlp_thumbnails(thumbnails)

    if not parsed:
        if allow_fallback and video_id:
            return generate_fallback_url(video_id, ThumbnailQuality.HIGH)
        return ""

    # Separate by orientation
    landscape = [t for t in parsed if is_landscape(t)]
    portrait = [t for t in parsed if is_portrait(t)]
    square = [t for t in parsed if is_square(t)]
    other = [t for t in parsed if not (is_landscape(t) or is_portrait(t) or is_square(t))]

    # Sort each group by quality preference
    def quality_key(t: ThumbnailInfo) -> int:
        try:
            return QUALITY_PREFERENCE.index(t.quality)
        except ValueError:
            return len(QUALITY_PREFERENCE)

    landscape.sort(key=quality_key)
    portrait.sort(key=quality_key)
    square.sort(key=quality_key)
    other.sort(key=quality_key)

    # Selection logic
    candidates = []
    if prefer_landscape:
        candidates.extend(landscape)
        candidates.extend(square)
        candidates.extend(other)
        candidates.extend(portrait)
    else:
        candidates.extend(parsed)  # Use original order (usually quality sorted)

    if candidates:
        return candidates[0].url

    # Fallback to generated URL
    if allow_fallback and video_id:
        return generate_fallback_url(video_id, ThumbnailQuality.HIGH)

    return ""


def generate_fallback_url(video_id: str, quality: ThumbnailQuality = ThumbnailQuality.HIGH) -> str:
    """
    Generate a predictable YouTube thumbnail URL from video ID.

    These URLs are stable and don't require yt-dlp.
    Note: maxresdefault and sddefault may return 404 for some videos.
    hqdefault is the most reliable.
    """
    if not video_id:
        return ""
    return YT_THUMB_BASE.format(video_id=video_id, quality=quality.value)


def generate_fallback_urls(video_id: str) -> dict[ThumbnailQuality, str]:
    """Generate all fallback URLs for a video ID."""
    return {
        quality: YT_THUMB_BASE.format(video_id=video_id, quality=quality.value)
        for quality in ThumbnailQuality
    }


def get_thumbnail_for_content_type(
    thumbnails: list[dict],
    video_id: str,
    content_type: str
) -> str:
    """
    Get appropriate thumbnail for content type.

    - Shorts: Often vertical, may need different handling
    - Live: May have special thumbnails
    - Regular video: Landscape preferred
    """
    if content_type == "short":
        # For Shorts, try to get portrait or square thumbnail
        parsed = parse_yt_dlp_thumbnails(thumbnails)
        portrait = [t for t in parsed if is_portrait(t)]
        square = [t for t in parsed if is_square(t)]

        def quality_key(t: ThumbnailInfo) -> int:
            try:
                return QUALITY_PREFERENCE.index(t.quality)
            except ValueError:
                return len(QUALITY_PREFERENCE)

        portrait.sort(key=quality_key)
        square.sort(key=quality_key)

        if portrait:
            return portrait[0].url
        if square:
            return square[0].url
        # Fall back to landscape
        return select_best_thumbnail(thumbnails, video_id, prefer_landscape=False)

    elif content_type == "live":
        # Live streams often have specific thumbnails
        return select_best_thumbnail(thumbnails, video_id, prefer_landscape=True)

    else:
        # Regular video - prefer landscape
        return select_best_thumbnail(thumbnails, video_id, prefer_landscape=True)


def validate_thumbnail_url(url: str, timeout: float = 5.0) -> bool:
    """
    Validate that a thumbnail URL is accessible (HEAD request).
    Use sparingly - adds network overhead.
    """
    if not url:
        return False
    try:
        import urllib.request
        req = urllib.request.Request(url, method="HEAD")
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status == 200
    except Exception:
        return False


def get_thumbnail_with_fallback_chain(
    thumbnails: list[dict],
    video_id: str,
    content_type: str = "video"
) -> list[str]:
    """
    Get a chain of thumbnail URLs to try in order (for client-side fallback).

    Returns list of URLs to try sequentially on error.
    """
    primary = get_thumbnail_for_content_type(thumbnails, video_id, content_type)
    fallbacks = generate_fallback_urls(video_id)

    chain = [primary]
    # Add fallbacks in quality order
    for q in QUALITY_PREFERENCE:
        fb_url = fallbacks[q]
        if fb_url and fb_url not in chain:
            chain.append(fb_url)

    # Add a generic placeholder as last resort
    chain.append("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='480' height='270' viewBox='0 0 480 270'%3E%3Crect fill='%23ddd' width='480' height='270'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' fill='%23999' font-family='sans-serif' font-size='16'%3ENo Thumbnail%3C/text%3E%3C/svg%3E")

    return chain


# ============ HTML HELPERS ============
def create_thumbnail_html(
    video_id: str,
    title: str,
    thumbnails: list[dict],
    content_type: str = "video",
    lazy: bool = True,
    aspect_ratio: str = "16/9"
) -> str:
    """
    Generate HTML for a thumbnail with fallback chain and lazy loading.

    Usage in template:
        <img src="{primary}" data-fallbacks='["url1", "url2", ...]' ...>
    """
    chain = get_thumbnail_with_fallback_chain(thumbnails, video_id, content_type)
    primary = chain[0]
    fallbacks = chain[1:]

    fallback_json = json_dumps(fallbacks)

    loading = "lazy" if lazy else "eager"
    alt_text = f"صورة مصغرة: {title}" if title else "فيديو يوتيوب"

    # Handle vertical Shorts
    if content_type == "short":
        aspect_ratio = "9/16"
        object_fit = "cover"
    else:
        object_fit = "cover"

    return f'''<img class="episode-thumb" src="{escape_html(primary)}" data-fallbacks="{escape_html(fallback_json)}" alt="{escape_html(alt_text)}" loading="{loading}" style="aspect-ratio: {aspect_ratio}; object-fit: {object_fit};" onerror="handleThumbnailError(this)">'''


def escape_html(text: str) -> str:
    """Escape HTML special characters."""
    if not text:
        return ""
    return (text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )



def json_dumps(obj) -> str:
    """JSON dump with minimal separators."""
    import json
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':'))


# ============ CLIENT-SIDE JAVASCRIPT ============
THUMBNAIL_ERROR_HANDLER_JS = """
function handleThumbnailError(img) {
    const fallbacks = JSON.parse(img.dataset.fallbacks || '[]');
    if (fallbacks.length > 0) {
        img.src = fallbacks.shift();
        img.dataset.fallbacks = JSON.stringify(fallbacks);
    } else {
        img.hidden = true;
        // Could show placeholder icon here
    }
}
"""


if __name__ == "__main__":
    # Quick test
    test_thumbs = [
        {"url": "https://i.ytimg.com/vi/abc123/maxresdefault.jpg", "width": 1280, "height": 720},
        {"url": "https://i.ytimg.com/vi/abc123/hqdefault.jpg", "width": 480, "height": 360},
        {"url": "https://i.ytimg.com/vi/abc123/mqdefault.jpg", "width": 320, "height": 180},
    ]
    print("Best:", select_best_thumbnail(test_thumbs, "abc123"))
    print("Fallback:", generate_fallback_url("abc123"))
    print("Chain:", get_thumbnail_with_fallback_chain(test_thumbs, "abc123"))