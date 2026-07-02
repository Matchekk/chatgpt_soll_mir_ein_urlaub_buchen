from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from utils import (
    CANDIDATE_COLUMNS,
    CANDIDATES_PATH,
    UNKNOWN,
    detect_platform,
    now_iso,
    read_csv,
    stable_id,
    write_csv,
)


def normalize_candidate(candidate: dict[str, Any]) -> dict[str, str]:
    row = {col: str(candidate.get(col, "") or "") for col in CANDIDATE_COLUMNS}
    url = row.get("url", "")
    row["candidate_id"] = row["candidate_id"] or stable_id(url or row.get("name", ""), "cand_")
    row["platform"] = row["platform"] or detect_platform(url)
    row["source"] = row["source"] or row["platform"] or UNKNOWN
    row["status"] = row["status"] or ("excluded" if row.get("excluded") == "true" else "candidate")
    row["last_updated"] = row["last_updated"] or now_iso()
    for key in ["name", "url", "location", "property_type"]:
        row[key] = row[key] or UNKNOWN
    return row


def upsert_candidate(candidate: dict[str, Any], csv_path: Path = CANDIDATES_PATH) -> None:
    df = read_csv(csv_path, CANDIDATE_COLUMNS)
    row = normalize_candidate(candidate)
    key = row["candidate_id"]
    if "candidate_id" not in df.columns:
        df["candidate_id"] = ""
    mask = df["candidate_id"].astype(str) == key
    if mask.any():
        idx = df.index[mask][0]
        for col, value in row.items():
            df.at[idx, col] = value
    else:
        df.loc[len(df)] = {col: row.get(col, "") for col in df.columns}
    write_csv(df, csv_path, CANDIDATE_COLUMNS)


def main() -> int:
    parser = argparse.ArgumentParser(description="Upsert a scored candidate JSON into costa-blanca-candidates.csv.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--csv", default=str(CANDIDATES_PATH))
    args = parser.parse_args()
    candidate = json.loads(Path(args.input).read_text(encoding="utf-8"))
    upsert_candidate(candidate, Path(args.csv))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
