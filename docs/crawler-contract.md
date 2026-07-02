# Crawler-to-Sheet Contract

This repo prepares machine-readable handoff files for ChatGPT. It does not write to Google Sheets directly and does not store Google credentials.

## Google Sheet target

```text
spreadsheet_id: 1WLQPMeByU0EMO7W8D9v6SuOeIBXVyXWXw07LexT-e_s
spreadsheet_name: Sommerurlaub Mati und Noa
preferred_sheet: Kandidaten
```

## Per-link outputs

For each processed link:

```text
data/raw/<link_id>.md
data/raw/<link_id>.html
data/raw/<link_id>.json
data/extracted/<link_id>.json
data/sheet-payloads/<link_id>.json
```

`data/raw/<link_id>.json` contains:

```json
{
  "source_url": "...",
  "link_id": "...",
  "platform": "airbnb | booking | other",
  "crawl_status": "success | blocked | failed",
  "status_code": 200,
  "success": true,
  "error": "",
  "raw_markdown_path": "data/raw/<link_id>.md",
  "raw_html_path": "data/raw/<link_id>.html",
  "screenshot_path": "data/screenshots/<link_id>.png"
}
```

## Latest run manifest

After every non-dry run:

```text
data/runs/latest.json
```

Schema:

```json
{
  "run_id": "timestamp-or-github-run-id",
  "started_at": "...",
  "finished_at": "...",
  "processed_count": 1,
  "success_count": 1,
  "blocked_count": 0,
  "failed_count": 0,
  "processed_links": [
    {
      "link_id": "...",
      "source_url": "...",
      "crawl_status": "success | blocked | failed | partial",
      "needs_manual_input": false,
      "candidate_id": "...",
      "extracted_json_path": "data/extracted/<link_id>.json",
      "sheet_payload_path": "data/sheet-payloads/<link_id>.json",
      "raw_markdown_path": "data/raw/<link_id>.md",
      "raw_html_path": "data/raw/<link_id>.html",
      "screenshot_path": "data/screenshots/<link_id>.png"
    }
  ]
}
```

## Sheet payload

`data/sheet-payloads/<link_id>.json` is the main ChatGPT handoff file:

```json
{
  "link_id": "...",
  "candidate_id": "...",
  "source_url": "...",
  "google_sheet_target": {
    "spreadsheet_id": "1WLQPMeByU0EMO7W8D9v6SuOeIBXVyXWXw07LexT-e_s",
    "spreadsheet_name": "Sommerurlaub Mati und Noa",
    "preferred_sheet": "Kandidaten"
  },
  "row": {
    "candidate_id": "...",
    "status": "...",
    "source": "...",
    "platform": "...",
    "name": "...",
    "url": "...",
    "date_range": "...",
    "nights": "...",
    "location": "...",
    "lat": "...",
    "lng": "...",
    "price_total": "...",
    "price_per_person": "...",
    "price_per_person_per_night": "...",
    "budget_under_500pp": "...",
    "rating": "...",
    "review_count": "...",
    "property_type": "...",
    "private_level": "...",
    "child_potential_0_10": "...",
    "quiet_score_0_10": "...",
    "review_evidence_0_10": "...",
    "beach_fit_0_10": "...",
    "transfer_score_0_10": "...",
    "budget_score_0_10": "...",
    "overall_score_0_10": "...",
    "crawl_status": "...",
    "needs_manual_input": "...",
    "raw_markdown_path": "...",
    "raw_html_path": "...",
    "raw_json_path": "...",
    "extracted_json_path": "...",
    "screenshot_path": "...",
    "excluded": "...",
    "exclusion_reason": "...",
    "notes": "...",
    "last_updated": "..."
  }
}
```

The payload row mirrors the candidate CSV columns and may include additional backend-only path columns such as `sheet_payload_path`.

## Blocking behavior

Do not bypass captchas, login walls, anti-bot systems, or access controls. If blocked or failed, still write a candidate, sheet payload and run manifest entry with:

```text
crawl_status = blocked | failed
needs_manual_input = true
```
