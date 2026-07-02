# Costa Blanca Travel-Research-System

Dieses Repo ist das Crawl- und Datenbackend fuer den Urlaub von Mati und Noa. GitHub crawlt Unterkunftslinks, speichert Rohdaten, extrahiert JSON, scored Kandidaten und erzeugt Handoff-Payloads. ChatGPT liest diese Payloads danach und schreibt die finale Zeile per Google-Sheets/Drive-Connector in das Google Sheet `Sommerurlaub Mati und Noa`.

## Finaler Workflow

```text
User sends link to ChatGPT.
ChatGPT adds link to GitHub intake or asks user to run workflow.
GitHub crawler writes latest run manifest and sheet payload JSON.
ChatGPT fetches sheet payload JSON from GitHub.
ChatGPT writes the final row into Google Sheet.
```

GitHub macht Crawling, Extraktion, Scoring und Artefakte. ChatGPT macht die finale Interpretation und den Sheet-Eintrag. Es werden keine Google-Credentials, Secrets oder Sheet-API-Schreibzugriffe im Repo gespeichert.

## Google Sheets

CSV-Live-Ansicht fuer Kandidaten:

```gs
=IMPORTDATA("https://raw.githubusercontent.com/Matchekk/chatgpt_soll_mir_ein_urlaub_buchen/main/data/costa-blanca-candidates.csv")
```

CSV-Live-Ansicht fuer Link Intake:

```gs
=IMPORTDATA("https://raw.githubusercontent.com/Matchekk/chatgpt_soll_mir_ein_urlaub_buchen/main/data/link-intake.csv")
```

Das Google Sheet bleibt das Live-Frontend. GitHub bleibt Crawl-/Datenbackend.

## Neue Links

Mati oder Noa schickt ChatGPT einen Airbnb-/Booking-/Unterkunftslink. ChatGPT traegt ihn in `data/link-intake.csv` ein oder nutzt lokal:

```bash
python scripts/crawl_links.py --url "https://www.airbnb.de/rooms/..." --submitted-by "Mati" --date-range "2026-09-04 to 2026-09-13" --notes "Airbnb von Noa"
```

Wichtige Intake-Spalten:

- `source_url`: Unterkunftslink
- `submitted_by`: `Mati`, `Noa` oder `cli`
- `status`: fuer neue Links `new`
- `date_range_hint`, `notes`, `priority`: Hinweise, die nicht durch `unknown` aus dem Extractor ueberschrieben werden

## Handoff-Dateien

Nach jedem echten Crawler-Lauf schreibt das Repo:

```text
data/runs/latest.json
data/sheet-payloads/<link_id>.json
data/raw/<link_id>.md
data/raw/<link_id>.html
data/raw/<link_id>.json
data/extracted/<link_id>.json
```

`data/runs/latest.json` sagt ChatGPT, welche Links neu verarbeitet wurden und welche Payload-Datei relevant ist. `data/sheet-payloads/<link_id>.json` enthaelt die finale Kandidatenzeile fuer das Google Sheet.

## Lokal ausfuehren

```bash
pip install -r requirements.txt
python scripts/crawl_links.py --dry-run
python scripts/smoke_test_pipeline.py
python scripts/validate_candidates.py
python scripts/build_excel.py
```

Weitere Varianten:

```bash
python scripts/crawl_links.py
python scripts/crawl_links.py --all
python scripts/crawl_links.py --only-new
python scripts/crawl_links.py --url "https://www.booking.com/hotel/..."
```

Die Excel-Datei liegt unter `exports/costa-blanca-matrix.xlsx` und wird aus CSV/JSON-Artefakten generiert. Sie sollte nicht manuell als Datenquelle editiert werden.

## GitHub Action

Die Action `Crawl accommodation links` ist manuell per `workflow_dispatch` startbar und laeuft bei Pushes auf `data/link-intake.csv`. Sie:

1. installiert Python und `requirements.txt`
2. crawlt neue Links
3. validiert Kandidaten
4. baut Excel
5. laedt `latest.json`, Sheet-Payloads und Excel als Artifact hoch
6. committet generierte Dateien nur, wenn sich etwas geaendert hat

Eine Endlosschleife wird vermieden, weil Pushes vom GitHub-Actions-Bot nicht erneut crawlen.

## Blocked und Manual Input

Keine Captcha-Umgehung, keine Anti-Bot-Umgehung, keine Fake-Identitaeten, keine illegalen Scraping-Tricks.

Wenn eine Seite blockt:

```text
crawl_status = blocked
needs_manual_input = true
```

Wenn wichtige Daten fehlen, entsteht trotzdem ein Kandidat und eine Sheet-Payload mit `needs_manual_input=true`. Dann sind manuelle Screenshots, Preis-/Datumsdaten oder Lageangaben noetig.

## Bewertung

Budgetannahme:

- 2 Erwachsene
- max. 500 EUR pro Person
- max. 1000 EUR Unterkunft gesamt

Reisezeitfenster:

- 04.09.2026 bis 18.09.2026
- maximal sinnvoll: 9 Naechte

Kinder-/Family-/Resort-Signale werden streng abgewertet. Harte Signale wie `Familienzimmer`, `Kinderbecken`, `Spielplatz`, `Wasserpark`, `Spielzimmer`, `Aparthotel` oder `Resort` fuehren zu `excluded=true`.

ALC/VLC-Distanzen sind Koordinaten-Schaetzungen:

```text
haversine distance * 1.23 road approximation
estimated_drive_minutes = road_km / 75 * 60
```

Das ist keine Live-Google-Maps-Fahrzeit.
