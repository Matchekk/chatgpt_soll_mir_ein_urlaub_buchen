from __future__ import annotations

import argparse
import asyncio
import base64
import os
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
    build_run_entry,
    detect_platform,
    ensure_directories,
    infer_nights,
    is_unknownish,
    known_value,
    now_iso,
    now_timestamp,
    read_csv,
    repo_relative,
    save_json,
    save_sheet_payload,
    stable_id,
    write_latest_run,
    write_csv,
)

BLOCKED_MARKERS = [
    "captcha",
    "verify you are human",
    "access denied",
    "request blocked",
    "temporarily blocked",
    "unusual traffic",
    "enable cookies",
    "robot check",
]

LISTING_MARKERS = [
    "/rooms/",
    "# apartment",
    "# villa",
    "# casa",
    "# bungalow",
    "alle fotos anzeigen",
    "show all photos",
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
        return {"crawl_status": "failed", "error": f"crawl4ai import failed: {exc}", "markdown": "", "html": "", "metadata": {}}

    try:
        async with AsyncWebCrawler() as crawler:
            result = await crawler.arun(url=url)
    except Exception as exc:
        return {"crawl_status": "failed", "error": str(exc), "traceback": traceback.format_exc(), "markdown": "", "html": "", "metadata": {}}

    markdown = getattr(result, "markdown", "") or getattr(result, "cleaned_html", "") or getattr(result, "html", "") or ""
    html = getattr(result, "html", "") or ""
    status_code = getattr(result, "status_code", None) or getattr(result, "status", None)
    success = bool(getattr(result, "success", bool(markdown or html)))
    error = getattr(result, "error_message", "") or getattr(result, "error", "")
    combined = f"{markdown}\n{html}\n{error}".lower()
    has_listing_content = any(marker in combined for marker in LISTING_MARKERS)
    blocked = status_code in {401, 403, 429} or (any(marker in combined for marker in BLOCKED_MARKERS) and not has_listing_content)
    crawl_status = "blocked" if blocked else ("success" if success and (markdown or html) else "failed")

    screenshot_path = ""
    screenshot = getattr(result, "screenshot", None)
    if screenshot:
        screenshot_path = "__pending__"

    metadata = {
        "source_url": url,
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


def candidate_from_link(
    row: dict[str, Any],
    crawl_status: str,
    manual: bool,
    raw_md: Path | None = None,
    raw_html: Path | None = None,
    raw_json: Path | None = None,
    extracted_json: Path | None = None,
    screenshot_path: str = "",
) -> dict[str, Any]:
    url = str(row.get("source_url", "")).strip()
    date_hint = row.get("date_range_hint") or UNKNOWN
    return {
        "candidate_id": stable_id(url, "cand_"),
        "status": crawl_status if crawl_status in {"blocked", "failed"} else "candidate",
        "source": row.get("platform") or detect_platform(url),
        "platform": row.get("platform") or detect_platform(url),
        "name": UNKNOWN,
        "url": url,
        "date_range": date_hint,
        "nights": infer_nights(date_hint) or UNKNOWN,
        "location": UNKNOWN,
        "crawl_status": crawl_status,
        "needs_manual_input": "true" if manual else "false",
        "raw_markdown_path": repo_relative(raw_md),
        "raw_html_path": repo_relative(raw_html),
        "raw_json_path": repo_relative(raw_json),
        "extracted_json_path": repo_relative(extracted_json),
        "screenshot_path": screenshot_path,
        "excluded": "false",
        "exclusion_reason": "",
        "notes": row.get("notes", ""),
        "last_updated": now_iso(),
    }


def process_extracted(
    row: dict[str, Any],
    extracted: dict[str, Any],
    crawl_status: str,
    raw_md: Path,
    raw_html: Path,
    raw_json: Path,
    extracted_json: Path,
    screenshot_path: str,
) -> dict[str, Any]:
    url = str(row.get("source_url", "")).strip()
    candidate = candidate_from_link(row, crawl_status, False, raw_md, raw_html, raw_json, extracted_json, screenshot_path)
    for key, value in extracted.items():
        if key in CANDIDATE_COLUMNS and not is_unknownish(value):
            candidate[key] = value
    if is_unknownish(candidate.get("date_range")):
        candidate["date_range"] = row.get("date_range_hint") or UNKNOWN
    if is_unknownish(candidate.get("nights")):
        candidate["nights"] = infer_nights(candidate.get("date_range")) or infer_nights(row.get("date_range_hint")) or UNKNOWN
    candidate["candidate_id"] = stable_id(url, "cand_")
    candidate["url"] = url
    candidate["source"] = row.get("platform") or candidate.get("platform") or detect_platform(url)
    candidate["platform"] = row.get("platform") or candidate.get("platform") or detect_platform(url)
    candidate["crawl_status"] = crawl_status
    critical_unknown = any(is_unknownish(candidate.get(key)) for key in ["price_total", "date_range", "nights"])
    candidate["needs_manual_input"] = "true" if critical_unknown else "false"
    candidate["raw_markdown_path"] = repo_relative(raw_md)
    candidate["raw_html_path"] = repo_relative(raw_html)
    candidate["raw_json_path"] = repo_relative(raw_json)
    candidate["extracted_json_path"] = repo_relative(extracted_json)
    candidate["screenshot_path"] = screenshot_path
    candidate["last_updated"] = now_iso()
    scored = score_candidate(candidate)
    scored["status"] = "excluded" if scored.get("excluded") == "true" else ("risk" if float(scored.get("child_potential_0_10", 0) or 0) >= 7 else "candidate")
    return scored


def finalize_candidate(link_id: str, row: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    url = str(row.get("source_url", "")).strip()
    payload_path = save_sheet_payload(link_id, url, candidate)
    candidate["sheet_payload_path"] = repo_relative(payload_path)
    upsert_candidate(candidate)
    manifest_status = candidate.get("crawl_status", "")
    if manifest_status == "success" and candidate.get("needs_manual_input") == "true":
        manifest_status = "partial"
    return build_run_entry(
        link_id=link_id,
        source_url=url,
        crawl_status=manifest_status,
        needs_manual_input=candidate.get("needs_manual_input") == "true",
        candidate_id=candidate.get("candidate_id", ""),
        extracted_json_path=candidate.get("extracted_json_path", ""),
        sheet_payload_path=candidate.get("sheet_payload_path", ""),
        raw_markdown_path=candidate.get("raw_markdown_path", ""),
        raw_html_path=candidate.get("raw_html_path", ""),
        screenshot_path=candidate.get("screenshot_path", ""),
    )


async def process_row(df, idx: int, dry_run: bool = False) -> dict[str, Any] | None:
    row = df.loc[idx].to_dict()
    url = str(row.get("source_url", "")).strip()
    link_id = str(row.get("link_id", "")).strip() or stable_id(url, "link_")
    platform = str(row.get("platform", "")).strip() or detect_platform(url)
    if not url:
        return None
    if dry_run:
        print(f"would process {link_id}: {url}", file=sys.stderr)
        return None

    df.at[idx, "status"] = "processing"
    df.at[idx, "crawl_status"] = "processing"
    df.at[idx, "last_updated"] = now_iso()
    write_csv(df, LINK_INTAKE_PATH, LINK_INTAKE_COLUMNS)

    raw_md = RAW_DIR / f"{link_id}.md"
    raw_html = RAW_DIR / f"{link_id}.html"
    raw_json = RAW_DIR / f"{link_id}.json"
    extracted_json = EXTRACTED_DIR / f"{link_id}.json"

    crawl = await crawl_with_crawl4ai(url)
    crawl_status = crawl.get("crawl_status", "failed")
    markdown = crawl.get("markdown", "") or ""
    html = crawl.get("html", "") or ""
    screenshot_path = write_screenshot(link_id, crawl.get("screenshot"))

    raw_md.write_text(markdown, encoding="utf-8", errors="replace")
    raw_html.write_text(html, encoding="utf-8", errors="replace")
    metadata = {
        **crawl.get("metadata", {}),
        "source_url": url,
        "link_id": link_id,
        "platform": platform,
        "crawl_status": crawl_status,
        "raw_markdown_path": repo_relative(raw_md),
        "raw_html_path": repo_relative(raw_html),
        "raw_json_path": repo_relative(raw_json),
        "screenshot_path": screenshot_path,
    }
    save_json(raw_json, metadata)

    if crawl_status in {"blocked", "failed"}:
        append_error(link_id, crawl_status, crawl.get("error", crawl_status), crawl.get("metadata", {}))
        candidate = candidate_from_link(row, crawl_status, True, raw_md, raw_html, raw_json, None, screenshot_path)
        run_entry = finalize_candidate(link_id, row, candidate)
        df.at[idx, "status"] = crawl_status
        df.at[idx, "crawl_status"] = crawl_status
        df.at[idx, "needs_manual_input"] = "true"
        df.at[idx, "last_updated"] = now_iso()
        return run_entry

    try:
        extraction = model_to_dict(extract_listing(url=url, platform=platform, raw_html=html, raw_markdown=markdown))
        save_json(extracted_json, extraction)
        candidate = process_extracted(row, extraction, crawl_status, raw_md, raw_html, raw_json, extracted_json, screenshot_path)
        run_entry = finalize_candidate(link_id, row, candidate)
        df.at[idx, "status"] = "done"
        df.at[idx, "crawl_status"] = "success"
        df.at[idx, "needs_manual_input"] = candidate.get("needs_manual_input", "false")
        df.at[idx, "last_updated"] = now_iso()
        return run_entry
    except Exception as exc:
        append_error(link_id, "extract-score-update", str(exc), {"traceback": traceback.format_exc()})
        candidate = candidate_from_link(row, "failed", True, raw_md, raw_html, raw_json, extracted_json, screenshot_path)
        run_entry = finalize_candidate(link_id, row, candidate)
        df.at[idx, "status"] = "failed"
        df.at[idx, "crawl_status"] = "failed"
        df.at[idx, "needs_manual_input"] = "true"
        df.at[idx, "last_updated"] = now_iso()
        return run_entry


async def run(args: argparse.Namespace) -> int:
    ensure_directories()
    started_at = now_timestamp()
    df = normalize_intake(read_csv(LINK_INTAKE_PATH, LINK_INTAKE_COLUMNS))
    target_link_id = ""
    if args.url:
        url = args.url.strip()
        link_id = stable_id(url, "link_")
        target_link_id = link_id
        existing = df["link_id"].astype(str) == link_id
        if existing.any():
            idx = df.index[existing][0]
            df.at[idx, "status"] = "new"
            df.at[idx, "submitted_by"] = args.submitted_by or df.at[idx, "submitted_by"] or "cli"
            if args.date_range:
                df.at[idx, "date_range_hint"] = args.date_range
            if args.notes:
                df.at[idx, "notes"] = args.notes
            if args.priority:
                df.at[idx, "priority"] = args.priority
            df.at[idx, "platform"] = detect_platform(url)
            df.at[idx, "last_updated"] = now_iso()
        else:
            df.loc[len(df)] = {
                "link_id": link_id,
                "status": "new",
                "submitted_by": args.submitted_by or "cli",
                "source_url": url,
                "platform": detect_platform(url),
                "date_range_hint": args.date_range or "",
                "notes": args.notes or "",
                "priority": args.priority or "",
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
        if target_link_id:
            if str(row.get("link_id", "")).strip() == target_link_id:
                candidates.append(idx)
        elif (args.all and status != "ignored") or status == "new":
            candidates.append(idx)

    if args.dry_run:
        print(f"{len(candidates)} link(s) would be processed.", file=sys.stderr)
    processed_links: list[dict[str, Any]] = []
    for idx in candidates:
        entry = await process_row(df, idx, args.dry_run)
        if entry:
            processed_links.append(entry)

    if not args.dry_run:
        write_csv(df, LINK_INTAKE_PATH, LINK_INTAKE_COLUMNS)
        run_id = os.environ.get("GITHUB_RUN_ID") or started_at
        write_latest_run(
            {
                "run_id": run_id,
                "started_at": started_at,
                "finished_at": now_timestamp(),
                "processed_count": len(processed_links),
                "success_count": sum(1 for item in processed_links if item.get("crawl_status") == "success"),
                "blocked_count": sum(1 for item in processed_links if item.get("crawl_status") == "blocked"),
                "failed_count": sum(1 for item in processed_links if item.get("crawl_status") == "failed"),
                "processed_links": processed_links,
            }
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Crawl new accommodation links and update the Costa Blanca candidate matrix.")
    parser.add_argument("--all", action="store_true", help="Process all non-ignored links, not only status=new.")
    parser.add_argument("--only-new", action="store_true", help="Process only status=new links. This is the default.")
    parser.add_argument("--url", default="", help="Process one URL and add it to link-intake.csv if missing.")
    parser.add_argument("--submitted-by", default="", help="Submitter for --url, e.g. Mati or Noa.")
    parser.add_argument("--date-range", default="", help="Date range hint for --url.")
    parser.add_argument("--notes", default="", help="Notes for --url.")
    parser.add_argument("--priority", default="", help="Priority for --url.")
    parser.add_argument("--dry-run", action="store_true", help="Show what would run without crawling or writing files.")
    args = parser.parse_args()
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
