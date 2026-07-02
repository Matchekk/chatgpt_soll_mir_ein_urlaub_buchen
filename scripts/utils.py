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
EXPORTS_DIR = ROOT / "exports"

LINK_INTAKE_PATH = DATA_DIR / "link-intake.csv"
CANDIDATES_PATH = DATA_DIR / "costa-blanca-candidates.csv"
EXCEL_PATH = EXPORTS_DIR / "costa-blanca-matrix.xlsx"

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
    "raw_json_path",
    "screenshot_path",
    "excluded",
    "exclusion_reason",
    "notes",
    "last_updated",
]


def ensure_directories() -> None:
    for path in [DATA_DIR, RAW_DIR, EXTRACTED_DIR, SCREENSHOTS_DIR, ERRORS_DIR, EXPORTS_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def now_iso() -> str:
    return datetime.now(timezone.utc).date().isoformat()


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
