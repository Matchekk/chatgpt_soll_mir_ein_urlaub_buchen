# Travel Research Workflow

Dieses Repo ist das Backend fuer den ChatGPT-zu-Google-Sheet-Workflow.

## Rollen

- GitHub: crawlt Links, speichert Raw Markdown/HTML/Metadata, extrahiert JSON, scored Kandidaten, baut Excel und Handoff-Payloads.
- ChatGPT: liest `data/runs/latest.json`, prueft die finale Entscheidung und schreibt die Payload-Zeile per Google-Sheets/Drive-Connector in `Sommerurlaub Mati und Noa`.
- Google Sheet: bleibt das Live-Frontend fuer Mati und Noa.

## Ablauf

1. Mati oder Noa schickt ChatGPT einen Unterkunftslink.
2. ChatGPT ergaenzt `data/link-intake.csv` oder startet lokal/remote `scripts/crawl_links.py --url`.
3. GitHub Action oder lokaler Crawler verarbeitet neue Links mit `status=new`.
4. Pro Link entstehen:

```text
data/raw/<link_id>.md
data/raw/<link_id>.html
data/raw/<link_id>.json
data/extracted/<link_id>.json
data/sheet-payloads/<link_id>.json
```

5. Nach dem Lauf entsteht:

```text
data/runs/latest.json
```

6. ChatGPT liest `latest.json`, oeffnet die dort referenzierte Sheet-Payload und schreibt die finale Zeile ins Google Sheet.

## Lokal

```bash
pip install -r requirements.txt
python scripts/crawl_links.py --dry-run
python scripts/smoke_test_pipeline.py
python scripts/validate_candidates.py
python scripts/build_excel.py
```

Echte Links:

```bash
python scripts/crawl_links.py --url "https://www.airbnb.de/rooms/..." --submitted-by "Mati" --date-range "2026-09-04 to 2026-09-13" --notes "Airbnb von Noa"
python scripts/crawl_links.py --all
python scripts/crawl_links.py --only-new
```

## Statusregeln

- `success`: Crawler hat verwertbare Seite gelesen.
- `partial`: Crawler war erfolgreich, aber Preis/Datum/Naechte fehlen und ChatGPT braucht manuelle Eingabe.
- `blocked`: Seite blockiert, Captcha/Login/Bot-Check oder Zugriff verweigert.
- `failed`: technischer Fehler.

Bei `blocked` oder `failed` gilt immer:

```text
needs_manual_input = true
```

## Kein Anti-Bot-Bypass

Das System umgeht keine Captchas, Login-Walls, Bot-Checks oder Zugriffskontrollen. Wenn blockiert wird, entstehen trotzdem ein Kandidat, Error-JSON und Manifest-Eintrag, damit ChatGPT und Mati/Noa sehen, dass der Link geprueft wurde.

## Excel

`exports/costa-blanca-matrix.xlsx` wird aus CSV/JSON-Artefakten gebaut. Nicht manuell als Datenquelle editieren, sondern CSV/Intake/Handoff-Dateien aktualisieren und `python scripts/build_excel.py` erneut ausfuehren.
