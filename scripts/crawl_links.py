from __future__ import annotations

import argparse
import asyncio
import base64
import sys
import traceback
from pathlib import Path
from typing import Any

from extract_listing import extract_listing, model_to_dict
from score_candidate import score_candidate
from update_candidates_csv import upsert_candidate
from utils import (
    CANDIDATE_COLUMNS,
    EXTRACTED_DIR,
    LINK_INTAKE_COLUMNS,
    LINK_INTAKE_PATH,
    RAW_DIR,
    SCREENSHOTS_DIR,
    UNKNOWN,
    append_error,
    detect_platform,
    ensure_directories,
    now_iso,
    read_csv,
    repo_relative,
    save_json,
    stable_id,
    write_csv,
)

BLOCKED_MARKERS = [
    "captcha",
    "verify you are human",
    "access denied",
    "blocked",
    "unusual traffic",
    "enable cookies",
    "robot check",
]


def normalize_intake(df):
    for col in LINK_INTAKE_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    for idx, row in df.iterrows():
        url = str(row.get("source_url", "")).strip()
        if not str(row.get("status", "")).strip():
            df.at[idx, "status"] = "new" if url else "ignored"
        if url:
            if not str(row.get("link_id", "")).strip():
                df.at[idx, "link_id"] = stable_id(url, "link_")
            df.at[idx, "platform"] = str(row.get("platform", "")).strip() or detect_platform(url)
        if not str(row.get("reviewed", "")).strip():
            df.at[idx, "reviewed"] = "false"
        if not str(row.get("needs_manual_input", "")).strip():
            df.at[idx, "needs_manual_input"] = "false"
        if not str(row.get("last_updated", "")).strip():
            df.at[idx, "last_updated"] = now_iso()
    return df


async def crawl_with_crawl4ai(url: str) -> dict[str, Any]:
    try:
        from crawl4ai import AsyncWebCrawler
    except Exception as exc:
        return {"crawl_status": "failed", "error": f"crawl4ai import failed: {exc}", "markdown": "", "metadata": {}}

    try:
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url)
    except Exception as exc:
        return {"crawl_status": "failed", "error": str(exc), "traceback": traceback.format_exc(), "markdown": "", "metadata": {}}

    markdown = getattr(result, "markdown", "") or getattr(result, "cleaned_html", "") or getattr(result, "html", "") or ""
    html = getattr(result, "html", "") or ""
    status_code = getattr(result, "status_code", None) or getattr(result, "status", None)
    success = bool(getattr(result, "success", bool(markdown or html)))
    error = getattr(result, "error_message", "") or getattr(result, "error", "")
    combined = f"{markdown}\n{html}\n{error}".lower()
    blocked = status_code in {401, 403, 429} or any(marker in combined for marker in BLOCKED_MARKERS)
    crawl_status = "blocked" if blocked else ("success" if success and (markdown or html) else "failed")

    screenshot_path = ""
    screenshot = getattr(result, "screenshot", None)
    if screenshot:
        screenshot_path = "__pending__"

    metadata = {
        "url": url,
        "status_code": status_code,
        "success": success,
        "error": str(error or ""),
        "crawl_status": crawl_status,
    }
    return {
        "crawl_status": crawl_status,
        "markdown": markdown or html,
        "html": html,
        "metadata": metadata,
        "screenshot": screenshot,
        "screenshot_path": screenshot_path,
    }


def write_screenshot(link_id: str, screenshot: Any) -> str:
    if not screenshot:
        return ""
    path = SCREENSHOTS_DIR / f"{link_id}.png"
    try:
        if isinstance(screenshot, bytes):
            path.write_bytes(screenshot)
        elif isinstance(screenshot, str):
            payload = screenshot.split(",", 1)[-1] if screenshot.startswith("data:image") else screenshot
            path.write_bytes(base64.b64decode(payload))
        else:
            return ""
    except Exception:
        return ""
    return repo_relative(path)


def candidate_from_link(row: dict[str, Any], crawl_status: str, manual: bool, raw_md: Path | None = None, raw_json: Path | None = None, screenshot_path: str = "") -> dict[str, Any]:
    url = str(row.get("source_url", "")).strip()
    return {
        "candidate_id": stable_id(url, "cand_"),
        "status": crawl_status if crawl_status in {"blocked", "failed"} else "candidate",
        "source": row.get("platform") or detect_platform(url),
        "platform": row.get("platform") or detect_platform(url),
        "name": UNKNOWN,
        "url": url,
        "date_range": row.get("date_range_hint") or UNKNOWN,
        "location": UNKNOWN,
        "crawl_status": crawl_status,
        "needs_manual_input": "true" if manual else "false",
        "raw_markdown_path": repo_relative(raw_md),
        "raw_json_path": repo_relative(raw_json),
        "screenshot_path": screenshot_path,
        "excluded": "false",
        "exclusion_reason": "",
        "notes": row.get("notes", ""),
        "last_updated": now_iso(),
    }


def process_extracted(row: dict[str, Any], extracted: dict[str, Any], crawl_status: str, raw_md: Path, raw_json: Path, screenshot_path: str) -> dict[str, Any]:
    url = str(row.get("source_url", "")).strip()
    candidate = candidate_from_link(row, crawl_status, False, raw_md, raw_json, screenshot_path)
    candidate.update({k: v for k, v in extracted.items() if k in CANDIDATE_COLUMNS})
    candidate["candidate_id"] = stable_id(url, "cand_")
    candidate["url"] = url
    candidate["source"] = row.get("platform") or candidate.get("platform") or detect_platform(url)
    candidate["platform"] = row.get("platform") or candidate.get("platform") or detect_platform(url)
    candidate["crawl_status"] = crawl_status
    candidate["needs_manual_input"] = "false"
    candidate["raw_markdown_path"] = repo_relative(raw_md)
    candidate["raw_json_path"] = repo_relative(raw_json)
    candidate["screenshot_path"] = screenshot_path
    candidate["last_updated"] = now_iso()
    scored = score_candidate(candidate)
    scored["status"] = "excluded" if scored.get("excluded") == "true" else ("risk" if float(scored.get("child_potential_0_10", 0) or 0) >= 7 else "candidate")
    return scored


async def process_row(df, idx: int, dry_run: bool = False) -> str:
    row = df.loc[idx].to_dict()
    url = str(row.get("source_url", "")).strip()
    link_id = str(row.get("link_id", "")).strip() or stable_id(url, "link_")
    platform = str(row.get("platform", "")).strip() or detect_platform(url)
    if not url:
        return "skipped-empty"
    if dry_run:
        print(f"would process {link_id}: {url}", file=sys.stderr)
        return "dry-run"

    df.at[idx, "status"] = "processing"
    df.at[idx, "crawl_status"] = "processing"
    df.at[idx, "last_updated"] = now_iso()
    write_csv(df, LINK_INTAKE_PATH, LINK_INTAKE_COLUMNS)

    raw_md = RAW_DIR / f"{link_id}.md"
    raw_json = RAW_DIR / f"{link_id}.json"
    extracted_json = EXTRACTED_DIR / f"{link_id}.json"

    crawl = await crawl_with_crawl4ai(url)
    crawl_status = crawl.get("crawl_status", "failed")
    markdown = crawl.get("markdown", "") or ""
    screenshot_path = write_screenshot(link_id, crawl.get("screenshot"))

    raw_md.write_text(markdown, encoding="utf-8", errors="replace")
    save_json(raw_json, {**crawl.get("metadata", {}), "link_id": link_id, "platform": platform})

    if crawl_status in {"blocked", "failed"}:
        append_error(link_id, crawl_status, crawl.get("error", crawl_status), crawl.get("metadata", {}))
        upsert_candidate(candidate_from_link(row, crawl_status, True, raw_md, raw_json, screenshot_path))
        df.at[idx, "status"] = crawl_status
        df.at[idx, "crawl_status"] = crawl_status
        df.at[idx, "needs_manual_input"] = "true"
        df.at[idx, "last_updated"] = now_iso()
        return crawl_status

    try:
        extraction = model_to_dict(extract_listing(markdown, url, platform))
        save_json(extracted_json, extraction)
        candidate = process_extracted(row, extraction, crawl_status, raw_md, raw_json, screenshot_path)
        upsert_candidate(candidate)
        df.at[idx, "status"] = "done"
        df.at[idx, "crawl_status"] = "success"
        df.at[idx, "needs_manual_input"] = "false"
        df.at[idx, "last_updated"] = now_iso()
        return "done"
    except Exception as exc:
        append_error(link_id, "extract-score-update", str(exc), {"traceback": traceback.format_exc()})
        upsert_candidate(candidate_from_link(row, "failed", True, raw_md, raw_json, screenshot_path))
        df.at[idx, "status"] = "failed"
        df.at[idx, "crawl_status"] = "failed"
        df.at[idx, "needs_manual_input"] = "true"
        df.at[idx, "last_updated"] = now_iso()
        return "failed"


async def run(args: argparse.Namespace) -> int:
    ensure_directories()
    df = normalize_intake(read_csv(LINK_INTAKE_PATH, LINK_INTAKE_COLUMNS))
    if args.url:
        url = args.url.strip()
        link_id = stable_id(url, "link_")
        existing = df["link_id"].astype(str) == link_id
        if existing.any():
            idx = df.index[existing][0]
            df.at[idx, "status"] = "new"
        else:
            df.loc[len(df)] = {
                "link_id": link_id,
                "status": "new",
                "submitted_by": "cli",
                "source_url": url,
                "platform": detect_platform(url),
                "date_range_hint": "",
                "notes": "",
                "priority": "",
                "crawl_status": "",
                "needs_manual_input": "false",
                "reviewed": "false",
                "last_updated": now_iso(),
            }
    if not args.dry_run:
        write_csv(df, LINK_INTAKE_PATH, LINK_INTAKE_COLUMNS)

    candidates = []
    for idx, row in df.iterrows():
        status = str(row.get("status", "")).strip().lower()
        url = str(row.get("source_url", "")).strip()
        if not url:
            continue
        if args.all or status == "new":
            candidates.append(idx)

    if args.dry_run:
        print(f"{len(candidates)} link(s) would be processed.", file=sys.stderr)
    for idx in candidates:
        await process_row(df, idx, args.dry_run)

    if not args.dry_run:
        write_csv(df, LINK_INTAKE_PATH, LINK_INTAKE_COLUMNS)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Crawl new accommodation links and update the Costa Blanca candidate matrix.")
    parser.add_argument("--all", action="store_true", help="Process all non-ignored links, not only status=new.")
    parser.add_argument("--url", default="", help="Process one URL and add it to link-intake.csv if missing.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would run without crawling or writing files.")
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
