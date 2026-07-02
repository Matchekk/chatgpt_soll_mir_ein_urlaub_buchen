from __future__ import annotations

import sys

from utils import CANDIDATE_COLUMNS, CANDIDATES_PATH, as_bool, parse_float, read_csv

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


def is_unknownish(value: str) -> bool:
    return str(value).strip().lower() in {"", "unknown", "not_available", "none"}


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

    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: {len(df)} candidate row(s) validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
