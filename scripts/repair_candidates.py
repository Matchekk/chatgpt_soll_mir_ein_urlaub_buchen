from __future__ import annotations

import re
from typing import Any

from score_candidate import score_candidate
from utils import (
    CANDIDATE_COLUMNS,
    CANDIDATES_PATH,
    LINK_INTAKE_COLUMNS,
    LINK_INTAKE_PATH,
    infer_nights,
    is_unknownish,
    parse_float,
    read_csv,
    save_sheet_payload,
    stable_id,
    write_csv,
)


def _fallback_total_from_intake(row: dict[str, Any]) -> float | None:
    text = f"{row.get('date_range_hint', '')} {row.get('notes', '')}".replace("\xa0", " ")
    pp_patterns = [
        r"([0-9][0-9., ]{0,10})\s*(?:€|eur)\s*(?:p\.?\s*p\.?|pp|pro\s+person|per\s+person)",
        r"(?:p\.?\s*p\.?|pp|pro\s+person|per\s+person)[^0-9]{0,20}([0-9][0-9., ]{0,10})\s*(?:€|eur)",
    ]
    total_patterns = [
        r"(?:gesamt|total|insgesamt)[^0-9]{0,30}([0-9][0-9., ]{0,10})\s*(?:€|eur)",
        r"([0-9][0-9., ]{0,10})\s*(?:€|eur)\s*(?:gesamt|total|insgesamt)",
    ]
    for pattern in pp_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = parse_float(match.group(1))
            if value is not None:
                return value * 2
    for pattern in total_patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            value = parse_float(match.group(1))
            if value is not None:
                return value
    return None


def _append_note(existing: str, note: str) -> str:
    existing = str(existing or "").strip()
    if note in existing:
        return existing
    return f"{existing} {note}".strip()


def main() -> int:
    candidates = read_csv(CANDIDATES_PATH, CANDIDATE_COLUMNS)
    intake = read_csv(LINK_INTAKE_PATH, LINK_INTAKE_COLUMNS)
    intake_by_url = {str(row.get("source_url", "")).strip(): row.to_dict() for _, row in intake.iterrows() if str(row.get("source_url", "")).strip()}

    changed = 0
    for idx, row in candidates.iterrows():
        candidate = row.to_dict()
        url = str(candidate.get("url", "")).strip()
        platform = str(candidate.get("platform", "")).strip().lower()
        price_total = parse_float(candidate.get("price_total"))
        intake_row = intake_by_url.get(url)

        repaired = False
        if platform == "airbnb" and price_total is not None and price_total < 100 and intake_row:
            fallback_total = _fallback_total_from_intake(intake_row)
            if fallback_total is not None and fallback_total >= 100:
                candidate["price_total"] = str(int(fallback_total)) if fallback_total.is_integer() else f"{fallback_total:.2f}"
                candidate["notes"] = _append_note(candidate.get("notes", ""), "Preis aus Intake-Hinweis übernommen; vor Buchung live prüfen.")
                repaired = True

        name = str(candidate.get("name", "")).lower()
        if platform == "airbnb" and "apartment" in name and str(candidate.get("property_type", "")).lower() == "villa":
            candidate["property_type"] = "apartment"
            repaired = True

        if is_unknownish(candidate.get("nights")) and intake_row:
            nights = infer_nights(intake_row.get("date_range_hint", ""))
            if nights:
                candidate["nights"] = nights
                repaired = True

        if repaired:
            scored = score_candidate(candidate)
            for col in CANDIDATE_COLUMNS:
                candidates.at[idx, col] = str(scored.get(col, "") or "")
            if intake_row:
                link_id = str(intake_row.get("link_id", "")).strip() or stable_id(url, "link_")
                save_sheet_payload(link_id, url, scored)
            changed += 1

    if changed:
        write_csv(candidates, CANDIDATES_PATH, CANDIDATE_COLUMNS)
    print(f"Repaired {changed} candidate row(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
