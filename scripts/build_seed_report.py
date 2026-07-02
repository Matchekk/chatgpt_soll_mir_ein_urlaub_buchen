from __future__ import annotations

import json

import pandas as pd

from utils import (
    CANDIDATE_COLUMNS,
    CANDIDATES_PATH,
    CODEX_SEEDS_PATH,
    DATA_DIR,
    SEED_REPORT_PATH,
    as_bool,
    is_plausible_price,
    parse_float,
    read_csv,
)


def load_summary(name: str) -> dict:
    path = DATA_DIR / "runs" / name
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def md_table(df: pd.DataFrame, cols: list[str], limit: int = 10) -> str:
    if df.empty:
        return "_Keine Einträge._"
    subset = df[cols].head(limit).fillna("")
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join(["---"] * len(cols)) + " |"]
    for _, row in subset.iterrows():
        lines.append("| " + " | ".join(str(row.get(col, "")).replace("|", "/") for col in cols) + " |")
    return "\n".join(lines)


def main() -> int:
    candidates = read_csv(CANDIDATES_PATH, CANDIDATE_COLUMNS)
    import_summary = load_summary("seed-import-summary.json")
    discovery_summary = load_summary("airbnb-discovery-summary.json")
    latest = load_summary("latest.json")

    candidates["_score"] = candidates["overall_score_0_10"].map(lambda value: parse_float(value) if parse_float(value) is not None else -1)
    candidates["_price"] = candidates["price_total"].map(lambda value: parse_float(value) if parse_float(value) is not None else 999999)
    top_score = candidates.sort_values("_score", ascending=False)
    under_budget = candidates[candidates["_price"] <= 1000].sort_values("_score", ascending=False)
    no_gos = candidates[candidates["excluded"].astype(str).str.lower().eq("true")]
    bad_prices = candidates[~candidates["price_total"].map(is_plausible_price)]
    manual = candidates[candidates["needs_manual_input"].astype(str).str.lower().eq("true")]
    recommendations = candidates[
        (candidates["excluded"].astype(str).str.lower() != "true")
        & (candidates["_price"] <= 1000)
    ].sort_values(["needs_manual_input", "_score"], ascending=[True, False]).head(5)

    seed_rows = import_summary.get("read", "unknown")
    if not CODEX_SEEDS_PATH.exists():
        seed_note = f"\n\nHinweis: Seed-Datei `{CODEX_SEEDS_PATH.as_posix()}` war im Checkout nicht vorhanden. Import/Discovery-Zahlen sind daher nur vorhandene Summary-Werte oder 0."
    else:
        seed_note = ""

    report = f"""# Codex Seed Crawl Report

## Zusammenfassung

- Seed-Zeilen gelesen: {seed_rows}
- Importiert: {import_summary.get("imported", 0)}
- Dedupliziert: {import_summary.get("duplicates", 0)}
- Übersprungen: {import_summary.get("skipped", 0)}
- Airbnb-Suchseiten verarbeitet: {discovery_summary.get("processed_search_seeds", 0)}
- Airbnb-Suchseiten mit Room-Links: {discovery_summary.get("seeds_with_rooms", 0)}
- Airbnb-Room-Links gefunden: {discovery_summary.get("rooms_found", 0)}
- Airbnb-Room-Links importiert: {discovery_summary.get("rooms_imported", 0)}
- Im letzten Lauf verarbeitet: {latest.get("processed_count", 0)}
- Erfolgreich gecrawlt: {latest.get("success_count", 0)}
- Blockiert: {latest.get("blocked_count", 0)}
- Fehlgeschlagen: {latest.get("failed_count", 0)}
- Kandidaten mit `needs_manual_input=true`: {len(manual)}
{seed_note}

## Top 10 Kandidaten nach Score

{md_table(top_score, ["name", "location", "price_total", "overall_score_0_10", "needs_manual_input", "url"])}

## Top 10 unter 1.000 EUR gesamt

{md_table(under_budget, ["name", "location", "price_total", "overall_score_0_10", "needs_manual_input", "url"])}

## Harte No-Gos

{md_table(no_gos, ["name", "location", "exclusion_reason", "family_red_flags", "url"], 50)}

## Einträge mit unplausiblem oder unbekanntem Preis

{md_table(bad_prices, ["name", "location", "price_total", "needs_manual_input", "notes", "url"], 50)}

## Nächste Empfehlung: zuerst manuell anschauen

{md_table(recommendations, ["name", "location", "price_total", "overall_score_0_10", "notes", "url"], 5)}
"""
    SEED_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    SEED_REPORT_PATH.write_text(report, encoding="utf-8")
    print(f"Built {SEED_REPORT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
