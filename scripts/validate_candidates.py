from __future__ import annotations

import json
import sys
from pathlib import Path

from utils import CANDIDATE_COLUMNS, CANDIDATES_PATH, ROOT, as_bool, is_unknownish, parse_float, read_csv

NUMERIC_OR_UNKNOWN = ["price_total", "nights"]
SCORE_COLUMNS = [
    "private_level",
    "child_potential_0_10",
    "quiet_score_0_10",
    "review_evidence_0_10",
    "beach_fit_0_10",
    "transfer_score_0_10",
    "budget_score_0_10",
    "overall_score_0_10",
]


def repo_file_exists(value: str) -> bool:
    if is_unknownish(value):
        return False
    return (ROOT / str(value)).exists()


def main() -> int:
    errors: list[str] = []
    df = read_csv(CANDIDATES_PATH, CANDIDATE_COLUMNS)

    missing = [col for col in CANDIDATE_COLUMNS if col not in df.columns]
    if missing:
        errors.append(f"Missing required columns: {', '.join(missing)}")

    ids = df["candidate_id"].astype(str).str.strip()
    duplicate_ids = sorted(set(ids[ids.duplicated() & (ids != "")]))
    if duplicate_ids:
        errors.append(f"Duplicate candidate_id values: {', '.join(duplicate_ids)}")

    for row_number, row in df.iterrows():
        label = f"row {row_number + 2}"
        if not str(row.get("candidate_id", "")).strip():
            errors.append(f"{label}: candidate_id is empty")
        if not str(row.get("url", "")).strip():
            errors.append(f"{label}: url is empty")
        for col in NUMERIC_OR_UNKNOWN:
            value = row.get(col, "")
            if not is_unknownish(value) and parse_float(value) is None:
                errors.append(f"{label}: {col} must be numeric or unknown")
        for col in SCORE_COLUMNS:
            value = row.get(col, "")
            if is_unknownish(value):
                continue
            number = parse_float(value)
            if number is None or not 0 <= number <= 10:
                errors.append(f"{label}: {col} must be between 0 and 10")
        child = row.get("child_potential_0_10", "")
        if not is_unknownish(child):
            number = parse_float(child)
            if number is None or not 0 <= number <= 10:
                errors.append(f"{label}: child_potential_0_10 must be between 0 and 10")
        if as_bool(row.get("excluded")) and is_unknownish(row.get("exclusion_reason", "")):
            errors.append(f"{label}: excluded=true needs exclusion_reason")
        price_pp = parse_float(row.get("price_per_person"))
        budget = str(row.get("budget_under_500pp", "")).strip().lower()
        if price_pp is not None and budget in {"true", "false"}:
            expected = "true" if price_pp <= 500 else "false"
            if budget != expected:
                errors.append(f"{label}: budget_under_500pp should be {expected}")
        crawl_status = str(row.get("crawl_status", "")).strip().lower()
        needs_manual = as_bool(row.get("needs_manual_input"))
        if crawl_status in {"blocked", "failed"} and not needs_manual:
            errors.append(f"{label}: crawl_status={crawl_status} requires needs_manual_input=true")
        if crawl_status == "success":
            extracted_path = row.get("extracted_json_path", "")
            if not repo_file_exists(extracted_path):
                errors.append(f"{label}: crawl_status=success requires existing extracted_json_path")
            if needs_manual and not any(is_unknownish(row.get(col, "")) for col in ["price_total", "date_range", "nights", "location", "lat", "lng", "name"]):
                errors.append(f"{label}: success + needs_manual_input=true needs missing price/date/nights/location/coordinate justification")
        raw_html_path = row.get("raw_html_path", "")
        if not is_unknownish(raw_html_path) and not repo_file_exists(raw_html_path):
            errors.append(f"{label}: raw_html_path does not exist: {raw_html_path}")
        came_from_crawl = crawl_status in {"success", "blocked", "failed", "partial"}
        if came_from_crawl:
            payload_path = row.get("sheet_payload_path", "")
            if not repo_file_exists(payload_path):
                errors.append(f"{label}: crawled candidate requires existing sheet_payload_path")
            else:
                try:
                    payload = json.loads((ROOT / str(payload_path)).read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    errors.append(f"{label}: sheet_payload_path is not valid JSON")
                else:
                    if is_unknownish(payload.get("link_id", "")):
                        errors.append(f"{label}: sheet payload missing link_id")
                    if payload.get("candidate_id") != row.get("candidate_id"):
                        errors.append(f"{label}: sheet payload candidate_id does not match CSV")

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: {len(df)} candidate row(s) validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
