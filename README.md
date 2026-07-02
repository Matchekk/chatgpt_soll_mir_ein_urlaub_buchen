# Costa Blanca Travel-Research-System

Dieses Repo sammelt Unterkunftslinks, crawlt sie ohne Anti-Bot-Umgehung, extrahiert konservativ strukturierte Daten, bewertet sie nach der Costa-Blanca-Matrix und erzeugt eine Google-Sheets-kompatible CSV plus eine fertige Excel-Auswertung.

## Google Sheets

Kandidaten in Google Sheets importieren:

```gs
=IMPORTDATA("https://raw.githubusercontent.com/Matchekk/chatgpt_soll_mir_ein_urlaub_buchen/main/data/costa-blanca-candidates.csv")
```

Link Intake importieren:

```gs
=IMPORTDATA("https://raw.githubusercontent.com/Matchekk/chatgpt_soll_mir_ein_urlaub_buchen/main/data/link-intake.csv")
```

## Neue Links eintragen

Mati oder Noa ergänzt `data/link-intake.csv`. Wichtig sind vor allem:

- `source_url`: Airbnb-, Booking- oder anderer Unterkunftslink
- `submitted_by`: `Mati` oder `Noa`
- `status`: für neue Links `new`
- `date_range_hint`, `notes`, `priority`: optional

`link_id` und `platform` werden automatisch ergänzt. Bereits verarbeitete Links werden nicht erneut gecrawlt, außer `status` wird wieder auf `new` gesetzt oder lokal `--all` genutzt wird.

## Lokal ausführen

```bash
pip install -r requirements.txt
python scripts/crawl_links.py
python scripts/validate_candidates.py
python scripts/build_excel.py
```

Nützliche Befehle:

```bash
python scripts/crawl_links.py --dry-run
python scripts/crawl_links.py --all
python scripts/crawl_links.py --url "https://www.airbnb.de/rooms/..."
```

Die Excel-Datei liegt danach unter `exports/costa-blanca-matrix.xlsx`.

## GitHub Action

Die Action `Crawl accommodation links` kann im GitHub-Tab **Actions** manuell gestartet werden. Sie läuft außerdem bei Änderungen an `data/link-intake.csv`.

Die Action:

1. installiert Python und `requirements.txt`
2. führt `python scripts/crawl_links.py` aus
3. validiert `data/costa-blanca-candidates.csv`
4. baut `exports/costa-blanca-matrix.xlsx`
5. committet generierte Änderungen nur, wenn wirklich Dateien geändert wurden

## Blocked und Manual Input

Das System macht keine Captcha-Umgehung, keine Anti-Bot-Umgehung, keine Fake-Identitäten und keine illegalen Scraping-Tricks.

Wenn Airbnb, Booking oder eine andere Seite blockt, wird sauber markiert:

```text
crawl_status = blocked
needs_manual_input = true
```

Bei technischen Fehlern wird `crawl_status=failed` gesetzt und ein Fehlerbericht in `data/errors/` gespeichert. Die Pipeline läuft weiter, damit ein geprüfter Link sichtbar bleibt.

## Bewertung

Die Matrix priorisiert Privatsphäre, wenig Kinder-/Family-Potenzial, Ruhe, Strandfit, Budget, Transfer und Review-Evidenz.

Budgetannahme:

- 2 Erwachsene
- max. 500 EUR pro Person
- max. 1000 EUR Unterkunft gesamt

Reisezeitfenster:

- 04.09.2026 bis 18.09.2026
- maximal sinnvoll: 9 Nächte

Explizite Kinder-/Family-/Resort-Signale werden streng abgewertet. Harte Begriffe wie `Familienzimmer`, `Kinderbecken`, `Spielplatz`, `Wasserpark`, `Spielzimmer`, `Aparthotel` oder `Resort` führen zu `excluded=true`.

## Flughäfen und Distanzen

Primärflughafen ist ALC, sekundär VLC. Distanzen werden grob über Koordinaten geschätzt:

```text
haversine distance * 1.23 road approximation
estimated_drive_minutes = road_km / 75 * 60
```

Das ist keine Live-Google-Maps-Fahrzeit.

## Excel

`exports/costa-blanca-matrix.xlsx` wird aus den CSVs erzeugt und sollte nicht manuell als Datenquelle bearbeitet werden. Änderungen gehören in:

- `data/link-intake.csv`
- `data/costa-blanca-candidates.csv`

Danach:

```bash
python scripts/build_excel.py
```

## Troubleshooting

Falls Crawl4AI oder Playwright lokal oder in GitHub Actions Probleme macht:

- `pip install -r requirements.txt` erneut ausführen
- lokal `python scripts/crawl_links.py --dry-run` testen
- Fehlerberichte in `data/errors/` prüfen
- bei blockierten Seiten die Zeile manuell mit Daten ergänzen und `needs_manual_input` später auf `false` setzen

Die CSV bleibt auch bei Crawl-Fehlern Google-Sheets-kompatibel.
