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
    if not text or text.lower() in {"unknown", "not_available", "none", "nan"}:
        return None
    text = text.replace("\xa0", " ")
    match = re.search(r"-?\d+(?:[.,]\d+)?", text.replace(" ", ""))
    if not match:
        return None
    return float(match.group(0).replace(",", "."))


def parse_int(value: Any) -> int | None:
    number = parse_float(value)
    return int(round(number)) if number is not None else None


def is_unknownish(value: Any) -> bool:
    return str(value or "").strip().lower() in {"", "unknown", "not_available", "none", "nan"}


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


def build_sheet_payload(link_id: str, source_url: str, candidate: dict[str, Any]) -> dict[str, Any]:
    row = {col: str(candidate.get(col, "") or "") for col in CANDIDATE_COLUMNS if col != "sheet_payload_path"}
    return {
        "link_id": link_id,
        "candidate_id": row.get("candidate_id", ""),
        "source_url": source_url,
        "google_sheet_target": GOOGLE_SHEET_TARGET,
        "row": row,
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
