from __future__ import annotations

import sys
from pathlib import Path

from extract_listing import extract_listing, model_to_dict
from score_candidate import score_candidate
from utils import (
    EXTRACTED_DIR,
    RAW_DIR,
    ROOT,
    build_run_entry,
    detect_platform,
    ensure_directories,
    now_iso,
    now_timestamp,
    repo_relative,
    save_json,
    save_sheet_payload,
    stable_id,
    write_latest_run,
)


def main() -> int:
    ensure_directories()
    source_url = "https://example.invalid/listings/quiet-cumbre-del-sol-apartment"
    link_id = "link_smoke_sample"
    candidate_id = stable_id(source_url, "cand_")

    fixture = ROOT / "tests" / "fixtures" / "sample_listing.html"
    html = fixture.read_text(encoding="utf-8")
    markdown = "# Quiet Cumbre del Sol Apartment\n\nPeaceful and quiet location near Cala Moraig. 8 nights total price EUR 920."

    raw_html = RAW_DIR / f"{link_id}.html"
    raw_md = RAW_DIR / f"{link_id}.md"
    raw_json = RAW_DIR / f"{link_id}.json"
    extracted_json = EXTRACTED_DIR / f"{link_id}.json"

    raw_html.write_text(html, encoding="utf-8")
    raw_md.write_text(markdown, encoding="utf-8")
    save_json(
        raw_json,
        {
            "source_url": source_url,
            "link_id": link_id,
            "platform": detect_platform(source_url),
            "crawl_status": "success",
            "status_code": 200,
            "success": True,
            "error": "",
            "raw_markdown_path": repo_relative(raw_md),
            "raw_html_path": repo_relative(raw_html),
            "raw_json_path": repo_relative(raw_json),
            "screenshot_path": "",
        },
    )

    extraction = model_to_dict(extract_listing(url=source_url, platform="other", raw_html=html, raw_markdown=markdown))
    save_json(extracted_json, extraction)

    candidate = {
        **extraction,
        "candidate_id": candidate_id,
        "status": "candidate",
        "source": "smoke-test",
        "platform": "other",
        "url": source_url,
        "date_range": "2026-09-04 to 2026-09-12",
        "nights": "8",
        "crawl_status": "success",
        "needs_manual_input": "false",
        "raw_markdown_path": repo_relative(raw_md),
        "raw_html_path": repo_relative(raw_html),
        "raw_json_path": repo_relative(raw_json),
        "extracted_json_path": repo_relative(extracted_json),
        "screenshot_path": "",
        "excluded": "false",
        "exclusion_reason": "",
        "notes": "Smoke test fixture; no external crawl.",
        "last_updated": now_iso(),
    }
    candidate = score_candidate(candidate)
    payload_path = save_sheet_payload(link_id, source_url, candidate)

    started_at = now_timestamp()
    write_latest_run(
        {
            "run_id": "smoke-test",
            "started_at": started_at,
            "finished_at": now_timestamp(),
            "processed_count": 1,
            "success_count": 1,
            "blocked_count": 0,
            "failed_count": 0,
            "processed_links": [
                build_run_entry(
                    link_id=link_id,
                    source_url=source_url,
                    crawl_status="success",
                    needs_manual_input=False,
                    candidate_id=candidate_id,
                    extracted_json_path=repo_relative(extracted_json),
                    sheet_payload_path=repo_relative(payload_path),
                    raw_markdown_path=repo_relative(raw_md),
                    raw_html_path=repo_relative(raw_html),
                    screenshot_path="",
                )
            ],
        }
    )

    print(f"OK: smoke payload written to {repo_relative(payload_path)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
