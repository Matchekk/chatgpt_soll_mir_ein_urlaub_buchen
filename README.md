# Costa Blanca Urlaubs-Matrix

Dieses Repo dient als CSV-Datenquelle fuer ein Google Sheet.

## Google-Sheets-Import

In Google Sheets in Zelle A1 einfuegen:

```gs
=IMPORTDATA("https://raw.githubusercontent.com/Matchekk/chatgpt_soll_mir_ein_urlaub_buchen/main/data/costa-blanca-candidates.csv")
```

Fuer neue Links / Intake:

```gs
=IMPORTDATA("https://raw.githubusercontent.com/Matchekk/chatgpt_soll_mir_ein_urlaub_buchen/main/data/link-intake.csv")
```

## Wichtige Logik

- Zeitraum-Fenster: 04.09.2026 bis 18.09.2026.
- Maximal sinnvoll: 9 Naechte.
- Unterkunftsbudget: maximal 500 EUR pro Person, also 1000 EUR gesamt fuer 2 Personen.
- Kinderpotenzial: 0 = sehr gut / kaum Risiko, 10 = schlimm.
- child/family No-Go-Begriffe fuehren zu `excluded=true`.
- ALC/VLC-Distanzen sind aktuell Naeherungen aus Koordinaten, keine Live-Google-Maps-Fahrzeiten.

## Workflow

1. Noa und Mati sammeln neue Links im Google Sheet oder schicken sie im Chat.
2. ChatGPT bewertet die Links.
3. ChatGPT aktualisiert `data/costa-blanca-candidates.csv`.
4. Google Sheets aktualisiert per IMPORTDATA.

## Rohdaten

- Kandidaten: `data/costa-blanca-candidates.csv`
- Neue Links: `data/link-intake.csv`
