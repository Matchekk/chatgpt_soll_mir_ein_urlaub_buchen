from __future__ import annotations

import csv
import hashlib
import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"
EXTRACTED_DIR = DATA_DIR / "extracted"
SCREENSHOTS_DIR = DATA_DIR / "screenshots"
ERRORS_DIR = DATA_DIR / "errors"
SHEET_PAYLOADS_DIR = DATA_DIR / "sheet-payloads"
RUNS_DIR = DATA_DIR / "runs"
EXPORTS_DIR = ROOT / "exports"

LINK_INTAKE_PATH = DATA_DIR / "link-intake.csv"
CANDIDATES_PATH = DATA_DIR / "costa-blanca-candidates.csv"
EXCEL_PATH = EXPORTS_DIR / "costa-blanca-matrix.xlsx"

GOOGLE_SHEET_TARGET = {
    "spreadsheet_id": "1WLQPMeByU0EMO7W8D9v6SuOeIBXVyXWXw07LexT-e_s",
    "spreadsheet_name": "Sommerurlaub Mati und Noa",
    "preferred_sheet": "Kandidaten",
}

UNKNOWN = "unknown"
TRUTHY = {"true", "1", "yes", "ja", "y"}
FALSY = {"false", "0", "no", "nein", "n"}
UNKNOWNISH = {"", "unknown", "unbekannt", "not_available", "nicht verfügbar", "nicht verfuegbar", "none", "nan"}

LINK_INTAKE_COLUMNS = [
    "link_id",
    "status",
    "submitted_by",
    "source_url",
    "platform",
    "date_range_hint",
    "notes",
    "priority",
    "crawl_status",
    "needs_manual_input",
    "reviewed",
    "last_updated",
]

CANDIDATE_COLUMNS = [
    "candidate_id",
    "status",
    "source",
    "platform",
    "name",
    "url",
    "date_range",
    "nights",
    "location",
    "lat",
    "lng",
    "price_total",
    "price_per_person",
    "price_per_person_per_night",
    "budget_under_500pp",
    "rating",
    "review_count",
    "property_type",
    "private_level",
    "child_potential_0_10",
    "quiet_score_0_10",
    "review_evidence_0_10",
    "beach_fit_0_10",
    "transfer_score_0_10",
    "budget_score_0_10",
    "overall_score_0_10",
    "alc_km_est",
    "alc_drive_min_est",
    "vlc_km_est",
    "vlc_drive_min_est",
    "airport_distance_method",
    "pool_type",
    "whole_place_evidence",
    "kitchen",
    "air_conditioning",
    "parking",
    "terrace_or_balcony",
    "family_red_flags",
    "quiet_evidence",
    "review_evidence",
    "crawl_status",
    "needs_manual_input",
    "raw_markdown_path",
    "raw_html_path",
    "raw_json_path",
    "extracted_json_path",
    "sheet_payload_path",
    "screenshot_path",
    "excluded",
    "exclusion_reason",
    "notes",
    "last_updated",
]

SHEET_DISPLAY_COLUMNS_DE = [
    "Bild",
    "Status",
    "Unterkunft",
    "Link",
    "Zeitraum",
    "Nächte",
    "Ort",
    "Gesamt €",
    "€ p.P.",
    "€ p.P./Nacht",
    "Budget",
    "Score",
    "Kinder",
    "Ruhe",
    "Strand",
    "Privat",
    "Reviews",
    "ALC km",
    "ALC min",
    "VLC km",
    "VLC min",
    "Pool",
    "Typ",
    "No-Go",
    "Notizen",
]

STATUS_DE = {
    "candidate": "Kandidat",
    "shortlist": "Shortlist",
    "backup": "Backup",
    "risk": "Risiko",
    "excluded": "Ausgeschlossen",
    "blocked": "Blockiert",
    "failed": "Fehlgeschlagen",
    "partial": "Teilweise",
    "done": "Erledigt",
    "new": "Neu",
    "processing": "In Verarbeitung",
}

PROPERTY_TYPE_DE = {
    "apartment": "Apartment / Wohnung",
    "holiday home": "Ferienhaus",
    "holiday house": "Ferienhaus",
    "bungalow": "Bungalow",
    "villa": "Villa",
    "hotel": "Hotel",
    "aparthotel": "Aparthotel",
    "room": "Zimmer",
}

POOL_TYPE_DE = {
    "private": "privat",
    "shared": "geteilt",
    "none": "kein Pool",
}

EXCLUSION_REASON_DE = {
    "family_no_go": "Kinder-/Familien-No-Go",
    "excluded": "Ausgeschlossen",
    "none": "Nein",
}


def ensure_directories() -> None:
    for path in [
        DATA_DIR,
        RAW_DIR,
        EXTRACTED_DIR,
        SCREENSHOTS_DIR,
        ERRORS_DIR,
        SHEET_PAYLOADS_DIR,
        RUNS_DIR,
        EXPORTS_DIR,
    ]:
        path.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def now_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_url(url: str) -> str:
    return (url or "").strip()


def stable_id(value: str, prefix: str = "") -> str:
    digest = hashlib.sha1(normalize_url(value).encode("utf-8")).hexdigest()[:12]
    return f"{prefix}{digest}" if prefix else digest


def detect_platform(url: str) -> str:
    host = urlparse(normalize_url(url)).netloc.lower()
    if "airbnb." in host:
        return "airbnb"
    if "booking." in host:
        return "booking"
    return "other"


def read_csv(path: Path, columns: list[str]) -> pd.DataFrame:
    if path.exists() and path.stat().st_size:
        df = pd.read_csv(path, dtype=str, keep_default_na=False)
    else:
        df = pd.DataFrame(columns=columns)

    if "source_type" in df.columns and "platform" not in df.columns:
        df["platform"] = df["source_type"]
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    extra_cols = [col for col in df.columns if col not in columns]
    return df[columns + extra_cols].fillna("")


def write_csv(df: pd.DataFrame, path: Path, columns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    for col in columns:
        if col not in df.columns:
            df[col] = ""
    df = df[columns].fillna("")
    df.to_csv(path, index=False, quoting=csv.QUOTE_MINIMAL, lineterminator="\n")


def load_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def as_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in TRUTHY:
        return True
    if text in FALSY:
        return False
    return default


def parse_float(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if text.lower() in UNKNOWNISH:
        return None
    text = text.replace("\xa0", " ").replace("€", " ").replace("EUR", " ").replace("eur", " ")
    match = re.search(r"-?\d+(?:[.,]\d+)?", text.replace(" ", ""))
    if not match:
        return None
    return float(match.group(0).replace(",", "."))


def parse_int(value: Any) -> int | None:
    number = parse_float(value)
    return int(round(number)) if number is not None else None


def is_unknownish(value: Any) -> bool:
    return str(value or "").strip().lower() in UNKNOWNISH


def known_value(value: Any) -> str:
    return "" if is_unknownish(value) else str(value).strip()


def infer_nights(text: Any) -> str:
    haystack = str(text or "")
    patterns = [
        r"(\d{1,2})\s*(?:nights|nächte|naechte)",
        r"(\d{1,2})\s*(?:night|nacht)",
    ]
    for pattern in patterns:
        match = re.search(pattern, haystack, flags=re.IGNORECASE)
        if match:
            return match.group(1)

    date_match = re.search(r"(\d{4}-\d{2}-\d{2})\s*(?:to|-|bis)\s*(\d{4}-\d{2}-\d{2})", haystack, flags=re.IGNORECASE)
    if date_match:
        try:
            start = datetime.fromisoformat(date_match.group(1))
            end = datetime.fromisoformat(date_match.group(2))
        except ValueError:
            return ""
        nights = (end - start).days
        return str(nights) if nights > 0 else ""
    return ""


def clamp(value: float, low: float = 0.0, high: float = 10.0) -> float:
    return max(low, min(high, value))


def fmt_number(value: float | int | None, digits: int = 1) -> str:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return UNKNOWN
    if digits == 0:
        return str(int(round(float(value))))
    return f"{float(value):.{digits}f}".rstrip("0").rstrip(".")


def repo_relative(path: Path | str | None) -> str:
    if not path:
        return ""
    path = Path(path)
    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def path_exists(repo_path: str) -> bool:
    if is_unknownish(repo_path):
        return False
    return (ROOT / repo_path).exists()


def _de_unknown(value: Any) -> str:
    return "unbekannt" if is_unknownish(value) else str(value).strip()


def _de_bool(value: Any) -> str:
    if is_unknownish(value):
        return "unbekannt"
    return "Ja" if as_bool(value) else "Nein"


def _de_lookup(value: Any, mapping: dict[str, str]) -> str:
    if is_unknownish(value):
        return "unbekannt"
    text = str(value).strip()
    return mapping.get(text.lower(), text)


def _format_de_number(value: Any, digits: int = 1, suffix: str = "") -> str:
    number = parse_float(value)
    if number is None:
        return "unbekannt"
    formatted = f"{number:,.{digits}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if digits > 0:
        formatted = formatted.rstrip("0").rstrip(",")
    return f"{formatted}{suffix}"


def _format_de_money(value: Any) -> str:
    number = parse_float(value)
    if number is None:
        return "unbekannt"
    return f"€ {_format_de_number(number, 2)}"


def _format_de_date_range(value: Any) -> str:
    text = _de_unknown(value)
    if text == "unbekannt":
        return text
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})\s*(?:to|-|bis)\s*(\d{4})-(\d{2})-(\d{2})", text, flags=re.IGNORECASE)
    if match:
        y1, m1, d1, y2, m2, d2 = match.groups()
        if y1 == y2:
            return f"{d1}.{m1}.–{d2}.{m2}.{y1}"
        return f"{d1}.{m1}.{y1}–{d2}.{m2}.{y2}"
    text = re.sub(r"\bnights\b", "Nächte", text, flags=re.IGNORECASE)
    text = re.sub(r"\bnight\b", "Nacht", text, flags=re.IGNORECASE)
    text = text.replace("user-provided", "User-Hinweis")
    return text


def _image_hint(candidate: dict[str, Any]) -> str:
    if as_bool(candidate.get("excluded")):
        return "⛔ No-Go"
    status = str(candidate.get("status", "")).strip().lower()
    location = str(candidate.get("location", "")).strip().lower()
    if status == "risk":
        return "⚠️ Risiko"
    if any(term in location for term in ["tarbena", "tàrbena", "beniarbeig", "inland"]):
        return "🏔️ Inland"
    price_pp = parse_float(candidate.get("price_per_person"))
    if price_pp is not None and price_pp <= 350:
        return "💸 Budget"
    if str(candidate.get("platform", "")).lower() == "airbnb":
        return "📷 Airbnb"
    return "🌊 Foto folgt"


def candidate_to_german_sheet_row(candidate: dict[str, Any]) -> dict[str, str]:
    reviews = "unbekannt"
    rating = _de_unknown(candidate.get("rating"))
    review_count = _de_unknown(candidate.get("review_count"))
    if rating != "unbekannt" and review_count != "unbekannt":
        reviews = f"{rating} · {review_count}"
    elif rating != "unbekannt":
        reviews = rating
    elif review_count != "unbekannt":
        reviews = f"{review_count} Bewertungen"

    no_go = "Ja" if as_bool(candidate.get("excluded")) else "Nein"
    notes = _de_unknown(candidate.get("notes"))
    if notes == "unbekannt":
        notes = ""
    exclusion = _de_lookup(candidate.get("exclusion_reason"), EXCLUSION_REASON_DE)
    if no_go == "Ja" and exclusion not in {"unbekannt", "Nein"} and exclusion not in notes:
        notes = f"{notes} Ausschlussgrund: {exclusion}.".strip()

    return {
        "Bild": _image_hint(candidate),
        "Status": _de_lookup(candidate.get("status"), STATUS_DE),
        "Unterkunft": _de_unknown(candidate.get("name")),
        "Link": _de_unknown(candidate.get("url")),
        "Zeitraum": _format_de_date_range(candidate.get("date_range")),
        "Nächte": _de_unknown(candidate.get("nights")),
        "Ort": _de_unknown(candidate.get("location")),
        "Gesamt €": _format_de_money(candidate.get("price_total")),
        "€ p.P.": _format_de_money(candidate.get("price_per_person")),
        "€ p.P./Nacht": _format_de_money(candidate.get("price_per_person_per_night")),
        "Budget": _de_bool(candidate.get("budget_under_500pp")),
        "Score": _format_de_number(candidate.get("overall_score_0_10"), 1),
        "Kinder": _format_de_number(candidate.get("child_potential_0_10"), 1),
        "Ruhe": _format_de_number(candidate.get("quiet_score_0_10"), 1),
        "Strand": _format_de_number(candidate.get("beach_fit_0_10"), 1),
        "Privat": _format_de_number(candidate.get("private_level"), 1),
        "Reviews": reviews,
        "ALC km": _format_de_number(candidate.get("alc_km_est"), 0),
        "ALC min": _format_de_number(candidate.get("alc_drive_min_est"), 0),
        "VLC km": _format_de_number(candidate.get("vlc_km_est"), 0),
        "VLC min": _format_de_number(candidate.get("vlc_drive_min_est"), 0),
        "Pool": _de_lookup(candidate.get("pool_type"), POOL_TYPE_DE),
        "Typ": _de_lookup(candidate.get("property_type"), PROPERTY_TYPE_DE),
        "No-Go": no_go,
        "Notizen": notes,
    }


def build_sheet_payload(link_id: str, source_url: str, candidate: dict[str, Any]) -> dict[str, Any]:
    row = {col: str(candidate.get(col, "") or "") for col in CANDIDATE_COLUMNS if col != "sheet_payload_path"}
    display_row_de = candidate_to_german_sheet_row(candidate)
    return {
        "link_id": link_id,
        "candidate_id": row.get("candidate_id", ""),
        "source_url": source_url,
        "google_sheet_target": GOOGLE_SHEET_TARGET,
        "row": row,
        "display_headers_de": SHEET_DISPLAY_COLUMNS_DE,
        "display_row_de": display_row_de,
    }


def save_sheet_payload(link_id: str, source_url: str, candidate: dict[str, Any]) -> Path:
    ensure_directories()
    payload_path = SHEET_PAYLOADS_DIR / f"{link_id}.json"
    candidate["sheet_payload_path"] = repo_relative(payload_path)
    payload = build_sheet_payload(link_id, source_url, candidate)
    payload["row"]["sheet_payload_path"] = repo_relative(payload_path)
    save_json(payload_path, payload)
    return payload_path


def build_run_entry(
    link_id: str,
    source_url: str,
    crawl_status: str,
    needs_manual_input: bool,
    candidate_id: str,
    extracted_json_path: str = "",
    sheet_payload_path: str = "",
    raw_markdown_path: str = "",
    raw_html_path: str = "",
    screenshot_path: str = "",
) -> dict[str, Any]:
    return {
        "link_id": link_id,
        "source_url": source_url,
        "crawl_status": crawl_status,
        "needs_manual_input": needs_manual_input,
        "candidate_id": candidate_id,
        "extracted_json_path": extracted_json_path,
        "sheet_payload_path": sheet_payload_path,
        "raw_markdown_path": raw_markdown_path,
        "raw_html_path": raw_html_path,
        "screenshot_path": screenshot_path,
    }


def write_latest_run(run: dict[str, Any]) -> Path:
    ensure_directories()
    latest_path = RUNS_DIR / "latest.json"
    save_json(latest_path, run)
    return latest_path


def append_error(link_id: str, stage: str, message: str, payload: dict[str, Any] | None = None) -> Path:
    ensure_directories()
    error_path = ERRORS_DIR / f"{link_id}-{stage}.json"
    save_json(
        error_path,
        {
            "link_id": link_id,
            "stage": stage,
            "message": message,
            "payload": payload or {},
            "last_updated": now_iso(),
        },
    )
    return error_path
