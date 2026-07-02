from __future__ import annotations

import argparse
import asyncio
import json
import re
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urljoin, urlparse, urlunparse

from crawl_links import crawl_with_crawl4ai
from utils import DATA_DIR, LINK_INTAKE_COLUMNS, LINK_INTAKE_PATH, append_error, detect_platform, ensure_directories, now_iso, read_csv, stable_id, write_csv

SUMMARY_PATH = DATA_DIR / "runs" / "airbnb-discovery-summary.json"
DATE_RANGE = "2026-09-08 to 2026-09-16"
BLOCKED_MARKERS = [
    "captcha",
    "robot",
    "unusual traffic",
    "access denied",
    "verify you are human",
    "blocked",
]


def is_airbnb_search_url(url: str) -> bool:
    parsed = urlparse(url)
    return "airbnb." in parsed.netloc.lower() and "/s/" in parsed.path.lower() and "/homes" in parsed.path.lower()


def normalize_room_url(url: str, base: str = "https://www.airbnb.de") -> str:
    absolute = urljoin(base, url)
    parsed = urlparse(absolute)
    match = re.search(r"/rooms/(\d+)", parsed.path)
    if not match:
        return ""
    path = f"/rooms/{match.group(1)}"
    query = dict(parse_qsl(parsed.query, keep_blank_values=False))
    keep = {
        "check_in": "2026-09-08",
        "check_out": "2026-09-16",
        "adults": "2",
        "guests": "2",
        "children": "0",
        "infants": "0",
        "pets": "0",
    }
    return urlunparse((parsed.scheme or "https", parsed.netloc or "www.airbnb.de", path, "", urlencode(keep), ""))


def extract_room_links(markup: str, base_url: str) -> list[str]:
    found = set()
    for match in re.finditer(r"(?:https?:)?//[^\"'\s<>]+/rooms/\d+[^\"'\s<>]*|/rooms/\d+[^\"'\s<>]*", markup):
        normalized = normalize_room_url(match.group(0), base_url)
        if normalized:
            found.add(normalized)
    return sorted(found)


async def main_async(args: argparse.Namespace) -> int:
    ensure_directories()
    intake = read_csv(LINK_INTAKE_PATH, LINK_INTAKE_COLUMNS)
    search_rows = []
    for idx, row in intake.iterrows():
        url = str(row.get("source_url", "")).strip()
        status = str(row.get("status", "")).strip().lower()
        if is_airbnb_search_url(url) and (args.all or status in {"search_seed", "new"}):
            search_rows.append((idx, row.to_dict()))

    summary = {"processed_search_seeds": 0, "seeds_with_rooms": 0, "rooms_found": 0, "rooms_imported": 0, "blocked_or_empty": 0}
    existing = {str(row.get("source_url", "")).strip() for _, row in intake.iterrows() if str(row.get("source_url", "")).strip()}
    for idx, row in search_rows:
        seed_url = str(row.get("source_url", "")).strip()
        summary["processed_search_seeds"] += 1
        crawl = await crawl_with_crawl4ai(seed_url)
        markup = "\n".join([crawl.get("markdown", "") or "", crawl.get("html", "") or ""])
        blocked = crawl.get("crawl_status") in {"blocked", "failed"} or any(marker in markup.lower() for marker in BLOCKED_MARKERS)
        links = [] if blocked else extract_room_links(markup, seed_url)
        if not links:
            summary["blocked_or_empty"] += 1
            intake.at[idx, "needs_manual_input"] = "true"
            intake.at[idx, "crawl_status"] = "blocked" if blocked else "partial"
            intake.at[idx, "last_updated"] = now_iso()
            append_error(str(row.get("link_id", "")) or stable_id(seed_url, "link_"), "airbnb-discovery", "No room links discovered or search page blocked.", {"source_url": seed_url, "crawl_status": crawl.get("crawl_status")})
            continue
        summary["seeds_with_rooms"] += 1
        summary["rooms_found"] += len(links)
        area_note = str(row.get("notes", "")).strip()
        for room_url in links:
            if room_url in existing:
                continue
            target = len(intake)
            intake.loc[target] = {col: "" for col in intake.columns}
            intake.at[target, "link_id"] = stable_id(room_url, "link_")
            intake.at[target, "status"] = "new"
            intake.at[target, "submitted_by"] = "Codex"
            intake.at[target, "source_url"] = room_url
            intake.at[target, "platform"] = "airbnb"
            intake.at[target, "date_range_hint"] = DATE_RANGE
            intake.at[target, "notes"] = f"Discovered from Airbnb search seed: {seed_url}. {area_note} 2 Erwachsene, keine Kinder."
            intake.at[target, "priority"] = row.get("priority", "high") or "high"
            intake.at[target, "crawl_status"] = ""
            intake.at[target, "needs_manual_input"] = "true"
            intake.at[target, "reviewed"] = "false"
            intake.at[target, "last_updated"] = now_iso()
            existing.add(room_url)
            summary["rooms_imported"] += 1
        intake.at[idx, "crawl_status"] = "success"
        intake.at[idx, "needs_manual_input"] = "false"
        intake.at[idx, "last_updated"] = now_iso()

    write_csv(intake, LINK_INTAKE_PATH, LINK_INTAKE_COLUMNS)
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover Airbnb /rooms links from search seed URLs.")
    parser.add_argument("--all", action="store_true", help="Process all Airbnb search URLs, not only search_seed/new.")
    args = parser.parse_args()
    return asyncio.run(main_async(args))


if __name__ == "__main__":
    raise SystemExit(main())
