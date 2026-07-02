from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from urllib.parse import urlparse

import pandas as pd

from utils import (
    CODEX_SEEDS_PATH,
    DATA_DIR,
    LINK_INTAKE_COLUMNS,
    LINK_INTAKE_PATH,
    detect_platform,
    ensure_directories,
    now_iso,
    read_csv,
    stable_id,
    write_csv,
)

SUMMARY_PATH = DATA_DIR / "runs" / "seed-import-summary.json"


def pick(row: pd.Series, names: list[str]) -> str:
    lower = {col.lower(): col for col in row.index}
    for name in names:
        if name.lower() in lower:
            return str(row.get(lower[name.lower()], "") or "").strip()
    return ""


def is_airbnb_search_url(url: str) -> bool:
    parsed = urlparse(url)
    return "airbnb." in parsed.netloc.lower() and "/s/" in parsed.path.lower() and "/homes" in parsed.path.lower()


def area_from_url_or_row(url: str, row: pd.Series) -> str:
    area = pick(row, ["area", "gebiet", "location", "region", "name"])
    if area:
        return area
    path = urlparse(url).path
    match = re.search(r"/s/([^/]+)/homes", path)
    return match.group(1).replace("-", " ") if match else ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Codex seed links into data/link-intake.csv.")
    parser.add_argument("--priority", action="append", default=[], help="Priority to import. Can be used multiple times.")
    parser.add_argument("--include-low", action="store_true", help="Include priority=low rows.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing non-done rows.")
    parser.add_argument("--seed-file", default=str(CODEX_SEEDS_PATH))
    args = parser.parse_args()

    ensure_directories()
    seed_path = Path(args.seed_file)
    allowed = {item.lower() for item in (args.priority or ["high"])}
    if args.include_low:
        allowed.add("low")
    if not allowed:
        allowed = {"high"}

    summary = {"seed_file": str(seed_path), "read": 0, "imported": 0, "skipped": 0, "duplicates": 0, "missing_seed_file": False}
    if not seed_path.exists():
        summary["missing_seed_file"] = True
        SUMMARY_PATH.parent.mkdir(parents=True, exist_ok=True)
        SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Seed file not found: {seed_path}")
        print(json.dumps(summary, indent=2))
        return 0

    seeds = pd.read_csv(seed_path, dtype=str, keep_default_na=False)
    summary["read"] = len(seeds)
    intake = read_csv(LINK_INTAKE_PATH, LINK_INTAKE_COLUMNS)
    existing_by_url = {str(row.get("source_url", "")).strip(): idx for idx, row in intake.iterrows() if str(row.get("source_url", "")).strip()}

    for _, row in seeds.iterrows():
        url = pick(row, ["source_url", "url", "link", "listing_url", "search_url"])
        if not url:
            summary["skipped"] += 1
            continue
        priority = (pick(row, ["priority", "prio"]) or "high").lower()
        if priority not in allowed:
            summary["skipped"] += 1
            continue
        platform = pick(row, ["platform"]) or detect_platform(url)
        notes = pick(row, ["notes", "note", "beschreibung"])
        area = area_from_url_or_row(url, row)
        if is_airbnb_search_url(url):
            status = "search_seed"
            notes = f"{notes} Airbnb search seed; area={area}; resolve via discover_airbnb_rooms.py.".strip()
        else:
            status = "new"
        date_range = pick(row, ["date_range_hint", "date_range"]) or "2026-09-08 to 2026-09-16"
        link_id = pick(row, ["link_id"]) or stable_id(url, "link_")

        if url in existing_by_url:
            idx = existing_by_url[url]
            existing_status = str(intake.at[idx, "status"]).lower()
            summary["duplicates"] += 1
            if existing_status == "done" and not args.force:
                continue
            if not args.force and existing_status not in {"", "new", "search_seed", "failed", "blocked"}:
                continue
            target_idx = idx
        else:
            target_idx = len(intake)
            intake.loc[target_idx] = {col: "" for col in intake.columns}

        intake.at[target_idx, "link_id"] = link_id
        intake.at[target_idx, "status"] = status
        intake.at[target_idx, "submitted_by"] = pick(row, ["submitted_by"]) or "Codex"
        intake.at[target_idx, "source_url"] = url
        intake.at[target_idx, "platform"] = platform
        intake.at[target_idx, "date_range_hint"] = date_range
        intake.at[target_idx, "notes"] = notes
        intake.at[target_idx, "priority"] = priority
        intake.at[target_idx, "crawl_status"] = ""
        intake.at[target_idx, "needs_manual_input"] = "true" if status == "search_seed" else "false"
        intake.at[target_idx, "reviewed"] = "false"
        intake.at[target_idx, "last_updated"] = now_iso()
        if url not in existing_by_url:
            summary["imported"] += 1
            existing_by_url[url] = target_idx

    write_csv(intake, LINK_INTAKE_PATH, LINK_INTAKE_COLUMNS)
    SUMMARY_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
