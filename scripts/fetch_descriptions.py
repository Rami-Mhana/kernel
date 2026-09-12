# scripts/fetch_descriptions.py
import subprocess
import json
import csv
import os
import sys
import time
from pathlib import Path

# Import shared description cleaning
sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
from content_schema import clean_description_for_classification

INPUT_CSV = "data/episodes_dahih_final_v2.csv"
OUTPUT_CSV = "data/episodes_dahih_with_desc.csv"
SLEEP_SECONDS = 1.5
MAX_DESC_LENGTH = 500


def load_existing_output():
    done = {}
    if os.path.exists(OUTPUT_CSV):
        with open(OUTPUT_CSV, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                done[row["url"]] = row
    return done


def fetch_description(url):
    cmd = ["yt-dlp", "--skip-download", "--print", "%(description)s"]
    result = subprocess.run(
        cmd + [url],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    )
    if result.returncode != 0:
        return ""
    return result.stdout.strip()


def main():
    with open(INPUT_CSV, encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames or [])
        if "description" not in fieldnames:
            fieldnames.append("description")
        rows = list(reader)

    done = load_existing_output()
    total = len(rows)

    output_path = Path(OUTPUT_CSV)
    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    with temp_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for i, row in enumerate(rows, 1):
            url = row["url"]
            if url in done:
                # Re-clean cached descriptions so improvements apply without
                # re-fetching 649 unchanged YouTube records.
                cached = clean_description_for_classification(done[url]["description"])
                row["description"] = cached.replace("\n", " ").strip()[:MAX_DESC_LENGTH]
                writer.writerow(row)
                continue

            try:
                raw_desc = fetch_description(url)
            except Exception as e:
                print(f"[{i}/{total}] Error: {e}")
                raw_desc = ""

            # Clean promotional text FIRST, then truncate
            cleaned_desc = clean_description_for_classification(raw_desc)
            cleaned_desc = cleaned_desc.replace("\n", " ").strip()[:MAX_DESC_LENGTH]

            row["description"] = cleaned_desc
            writer.writerow(row)
            f.flush()
            print(f"[{i}/{total}] {row['title'][:50]}")
            time.sleep(SLEEP_SECONDS)

    temp_path.replace(output_path)
    print(f"Done -> {OUTPUT_CSV}")


if __name__ == "__main__":
    main()