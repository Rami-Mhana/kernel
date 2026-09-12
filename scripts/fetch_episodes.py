#!/usr/bin/env python3
import argparse
import subprocess
import json
import csv
import os
import re

# عدّل القايمة دي بروابط القنوات الصح بعد ما تتأكد منها
CHANNELS = {
    "aj_kabrit": "https://www.youtube.com/@AJpluskibreet/videos",
    "new_media_life": "https://www.youtube.com/@NewMedia_Life/videos",
    "museum_of_the_future": "https://www.youtube.com/@museumofthefuture/videos"
    # "personal_channel": "PUT_URL_HERE",
    # "future_museum": "PUT_URL_HERE",
}

RAW_DIR = "data/raw"
OUTPUT_CSV = "data/episodes_3.csv"

os.makedirs(RAW_DIR, exist_ok=True)


def fetch_channel(name, url):
    """يسحب بيانات كل فيديوهات القناة كـ JSON عن طريق yt-dlp (بدون تحميل الفيديو)."""
    out_path = os.path.join(RAW_DIR, f"{name}.jsonl")
    cmd = [
        "yt-dlp",
        "--flat-playlist",
        "--dump-json",
        url,
    ]
    print(f"Data is being processed: {name} ...")
    with open(out_path, "w", encoding="utf-8") as f:
        result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        print(f"Warning: problem with{name}: {result.stderr[:300]}")
    return out_path


def parse_jsonl(path, channel_label):
    episodes = []
    if not os.path.exists(path):
        return episodes
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue
            episodes.append({
                "title": data.get("title", ""),
                "url": f"https://www.youtube.com/watch?v={data.get('id', '')}",
                "channel": channel_label,
                "domain": "",       # تملأها يدوي بعدين
                "watched": "",
                "extracted": "",
                "notes": "",
            })
    return episodes


def main():
    global RAW_DIR
    parser = argparse.ArgumentParser(
        description="Fetch video metadata from one or more YouTube channels or playlists."
    )
    parser.add_argument(
        "urls",
        nargs="*",
        help="YouTube channel or playlist URLs; omit to use the legacy CHANNELS list",
    )
    parser.add_argument("-o", "--output", default=OUTPUT_CSV, help="Output CSV path")
    parser.add_argument("--raw-dir", default=RAW_DIR, help="Directory for JSONL cache")
    args = parser.parse_args()

    RAW_DIR = args.raw_dir
    os.makedirs(RAW_DIR, exist_ok=True)

    if args.urls:
        sources = []
        for url in args.urls:
            if "youtube.com" not in url and "youtu.be" not in url:
                parser.error(f"Not a YouTube URL: {url}")
            slug = re.sub(r"[^\w\s-]", "", url, flags=re.UNICODE)
            slug = re.sub(r"[\s-]+", "-", slug.strip()).lower()[:50] or "youtube-source"
            sources.append((slug, url))
    else:
        sources = list(CHANNELS.items())

    all_episodes = []
    for name, url in sources:
        raw_path = fetch_channel(name, url)
        all_episodes.extend(parse_jsonl(raw_path, name))

    output_path = os.path.abspath(args.output)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        fieldnames = ["title", "url", "channel", "domain", "watched", "extracted", "notes"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_episodes)

    print(f"Done. Total episodes: {len(all_episodes)} -> {output_path}")


if __name__ == "__main__":
    main()