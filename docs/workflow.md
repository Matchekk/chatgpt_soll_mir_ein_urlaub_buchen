# Travel Research Workflow

Dieses Repo verarbeitet Unterkunftslinks in eine Google-Sheets-kompatible Costa-Blanca-Matrix.

## Ablauf

1. Mati oder Noa trägt einen Unterkunftslink in `data/link-intake.csv` ein.
2. `python scripts/crawl_links.py` verarbeitet Zeilen mit `status=new`.
3. Der Crawler speichert Rohdaten in `data/raw/`.
4. `extract_listing.py` extrahiert konservativ strukturierte Felder.
5. `score_candidate.py` berechnet Budget, Distanzen, Family-Risiko und Gesamtscore.
6. `update_candidates_csv.py` ergänzt oder aktualisiert `data/costa-blanca-candidates.csv`.
7. `build_excel.py` erzeugt `exports/costa-blanca-matrix.xlsx`.
8. Google Sheets kann die CSVs per `IMPORTDATA()` anzeigen.

## Kein Anti-Bot-Bypass

Das System umgeht keine Captchas, keine Bot-Checks und keine Zugriffsbeschränkungen. Wenn eine Seite blockt, wird der Link als geprüft markiert:

```text
crawl_status = blocked
needs_manual_input = true
```

Bei technischen Fehlern wird `crawl_status=failed` gesetzt und ein Fehlerbericht in `data/errors/` gespeichert.

## Lokal ausführen

```bash
pip install -r requirements.txt
python scripts/crawl_links.py
python scripts/validate_candidates.py
python scripts/build_excel.py
```

Nützliche Varianten:

```bash
python scripts/crawl_links.py --dry-run
python scripts/crawl_links.py --all
python scripts/crawl_links.py --url "https://www.airbnb.de/rooms/..."
```

## GitHub Action

Die Action `.github/workflows/crawl-links.yml` läuft manuell über `workflow_dispatch` oder wenn `data/link-intake.csv` geändert wird. Sie crawlt, validiert, baut Excel und committet nur dann zurück, wenn generierte Dateien geändert wurden.

## Scoring-Kurzfassung

Gewichte:

- `private_level`: 18 %
- `child_potential_inverse`: 18 %
- `quiet_score_0_10`: 18 %
- `beach_fit_0_10`: 14 %
- `transfer_score_0_10`: 10 %
- `budget_score_0_10`: 12 %
- `review_evidence_0_10`: 10 %

`child_potential_inverse = 10 - child_potential_0_10`. Wenn `excluded=true`, ist `overall_score_0_10 = 0`.

## Distanzen

ALC und VLC werden nur grob geschätzt:

```text
Haversine-Distanz * 1.23 Straßenfaktor
Fahrzeit = road_km / 75 * 60
```

Das ist keine Live-Google-Maps-Route.
