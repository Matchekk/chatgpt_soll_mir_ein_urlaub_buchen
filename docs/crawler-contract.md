# Crawler-to-Sheet Contract

This repo uses a two-step workflow:

1. GitHub crawler extracts listing data into JSON/Markdown.
2. ChatGPT reads the extracted data, calculates the travel score, and writes the final row into the shared Google Sheet.

## Runtime workflow

User sends ChatGPT a listing URL.

ChatGPT should:

1. Add the URL as a crawl request in `data/link-intake.csv` or pass it to the crawler workflow.
2. Trigger/request GitHub crawler execution if available.
3. Read the resulting JSON from `data/extracted/<link_id>.json` and Markdown from `data/raw/<link_id>.md`.
4. Calculate the final decision matrix.
5. Write/update the row in the Google Sheet `Sommerurlaub Mati und Noa`.

## Required crawler output

Each crawler run must write:

```text
 data/extracted/<link_id>.json
 data/raw/<link_id>.md
```

Optional:

```text
 data/screenshots/<link_id>.png
 data/errors/<link_id>.json
```

## JSON schema

```json
{
  "link_id": "stable hash or slug",
  "source_url": "https://example.com/listing",
  "platform": "airbnb | booking | other",
  "crawl_status": "success | blocked | failed | partial",
  "needs_manual_input": false,
  "fetched_at": "2026-07-02T00:00:00+02:00",
  "name": "Listing title or unknown",
  "location": "Listing location or unknown",
  "lat": null,
  "lng": null,
  "date_range": "2026-09-04 to 2026-09-13",
  "nights": 9,
  "price_total": null,
  "rating": null,
  "review_count": null,
  "property_type": "apartment | villa | holiday_home | bungalow | hotel | unknown",
  "whole_place_evidence": "exact text evidence or unknown",
  "kitchen": "true | false | unknown",
  "air_conditioning": "true | false | unknown",
  "parking": "true | false | unknown",
  "terrace_or_balcony": "true | false | unknown",
  "pool_type": "private | shared | none | unknown",
  "facilities": [],
  "family_red_flags": [],
  "quiet_evidence": [],
  "review_evidence": [],
  "raw_markdown_path": "data/raw/<link_id>.md",
  "screenshot_path": "data/screenshots/<link_id>.png",
  "error_message": null
}
```

## Blocking behavior

Do not bypass captchas, login walls, anti-bot systems, or access controls.

If blocked, the crawler must still write JSON:

```json
{
  "crawl_status": "blocked",
  "needs_manual_input": true,
  "source_url": "...",
  "error_message": "blocked by site / captcha / login required"
}
```

## ChatGPT scoring after crawler output

ChatGPT calculates:

- price_per_person
- price_per_person_per_night
- budget_under_500pp
- child_potential_0_10
- quiet_score_0_10
- review_evidence_0_10
- beach_fit_0_10
- transfer_score_0_10
- budget_score_0_10
- overall_score_0_10
- excluded
- exclusion_reason
- ALC/VLC approximate distance and drive time

## Google Sheet target

Shared spreadsheet:

```text
Sommerurlaub Mati und Noa
https://docs.google.com/spreadsheets/d/1WLQPMeByU0EMO7W8D9v6SuOeIBXVyXWXw07LexT-e_s/edit
```

Final rows are written by ChatGPT to the appropriate sheet/tab after scoring.
