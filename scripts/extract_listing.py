from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from utils import UNKNOWN, detect_platform, save_json

HARD_FAMILY_TERMS = [
    "familienzimmer",
    "family rooms",
    "kinderbecken",
    "kids pool",
    "children pool",
    "kinderclub",
    "kids club",
    "mini club",
    "kinderspielplatz",
    "playground",
    "spielzimmer",
    "game room",
    "indoorspielbereich",
    "outdoorspielgeräte",
    "aparthotel",
    "resort",
    "aqua park",
    "wasserpark",
    "entertainment team",
    "animation",
]

SOFT_FAMILY_TERMS = [
    "children",
    "child",
    "toddler",
    "baby",
    "treppenschutz",
    "brettspiele",
    "puzzle",
    "board games",
    "puzzles",
    "wasserspielzeug",
    "water toys",
    "family-friendly",
]


class ListingExtraction(BaseModel):
    name: str = UNKNOWN
    platform: str = UNKNOWN
    url: str = UNKNOWN
    location: str = UNKNOWN
    price_total: str = UNKNOWN
    date_range: str = UNKNOWN
    nights: str = UNKNOWN
    rating: str = UNKNOWN
    review_count: str = UNKNOWN
    property_type: str = UNKNOWN
    kitchen: str = UNKNOWN
    air_conditioning: str = UNKNOWN
    parking: str = UNKNOWN
    terrace_or_balcony: str = UNKNOWN
    pool_type: str = UNKNOWN
    whole_place_evidence: str = UNKNOWN
    family_red_flags: str = ""
    quiet_evidence: str = UNKNOWN
    review_evidence: str = UNKNOWN
    lat: str = UNKNOWN
    lng: str = UNKNOWN
    found_terms: list[str] = Field(default_factory=list)
    hard_family_red_flags: list[str] = Field(default_factory=list)
    soft_family_red_flags: list[str] = Field(default_factory=list)


def model_to_dict(model: BaseModel) -> dict[str, Any]:
    if hasattr(model, "model_dump"):
        return model.model_dump()
    return model.dict()


def _clean_text(text: str) -> str:
    if "<html" in text.lower() or "<body" in text.lower():
        soup = BeautifulSoup(text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text("\n")
    return re.sub(r"[ \t]+", " ", text).strip()


def _json_ld_payloads(raw: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(raw, "html.parser")
    payloads: list[dict[str, Any]] = []
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            parsed = json.loads(script.get_text(strip=True))
        except json.JSONDecodeError:
            continue
        candidates = parsed if isinstance(parsed, list) else [parsed]
        for item in candidates:
            if isinstance(item, dict):
                payloads.append(item)
                graph = item.get("@graph")
                if isinstance(graph, list):
                    payloads.extend(child for child in graph if isinstance(child, dict))
    return payloads


def _first_match(patterns: list[str], text: str) -> str:
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE)
        if match:
            return match.group(1).strip(" -:\n\t")
    return UNKNOWN


def _markdown_title(text: str) -> str:
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# "):
            title = stripped.lstrip("#").strip()
            if 5 <= len(title) <= 160:
                return title
    return UNKNOWN


def _contains_any(text: str, terms: list[str]) -> list[str]:
    text_l = text.lower()
    return [term for term in terms if term in text_l]


def _yes_unknown(text: str, terms: list[str]) -> str:
    return "true" if _contains_any(text, terms) else UNKNOWN


def _infer_property_type(text: str) -> str:
    checks = [
        ("villa", ["villa"]),
        ("holiday home", ["holiday home", "casa", "ferienhaus"]),
        ("bungalow", ["bungalow"]),
        ("apartment", ["apartment", "apartamento", "wohnung", "flat"]),
        ("hotel", ["hotel"]),
        ("aparthotel", ["aparthotel"]),
    ]
    text_l = text.lower()
    for label, terms in checks:
        if any(term in text_l for term in terms):
            return label
    return UNKNOWN


def _extract_from_json_ld(payloads: list[dict[str, Any]], result: dict[str, Any]) -> None:
    for payload in payloads:
        if result["name"] == UNKNOWN and payload.get("name"):
            result["name"] = str(payload["name"])
        address = payload.get("address")
        if result["location"] == UNKNOWN:
            if isinstance(address, dict):
                result["location"] = ", ".join(str(address.get(k, "")) for k in ["addressLocality", "addressRegion", "addressCountry"] if address.get(k)) or UNKNOWN
            elif isinstance(address, str):
                result["location"] = address
        geo = payload.get("geo")
        if isinstance(geo, dict):
            if result["lat"] == UNKNOWN and geo.get("latitude") is not None:
                result["lat"] = str(geo["latitude"])
            if result["lng"] == UNKNOWN and geo.get("longitude") is not None:
                result["lng"] = str(geo["longitude"])
        aggregate = payload.get("aggregateRating")
        if isinstance(aggregate, dict):
            if result["rating"] == UNKNOWN and aggregate.get("ratingValue") is not None:
                result["rating"] = str(aggregate["ratingValue"])
            if result["review_count"] == UNKNOWN and aggregate.get("reviewCount") is not None:
                result["review_count"] = str(aggregate["reviewCount"])
        offers = payload.get("offers")
        if isinstance(offers, dict) and result["price_total"] == UNKNOWN and offers.get("price") is not None:
            result["price_total"] = str(offers["price"])


def extract_listing(
    raw: str = "",
    url: str = "",
    platform: str | None = None,
    raw_html: str = "",
    raw_markdown: str = "",
) -> ListingExtraction:
    if raw and not raw_html and not raw_markdown:
        if "<html" in raw.lower() or "<body" in raw.lower():
            raw_html = raw
        else:
            raw_markdown = raw
    combined_raw = "\n".join(part for part in [raw_html, raw_markdown] if part)
    text = _clean_text(combined_raw)
    compact = re.sub(r"\s+", " ", text)
    lower = compact.lower()
    hard_terms = _contains_any(compact, HARD_FAMILY_TERMS)
    soft_terms = _contains_any(compact, SOFT_FAMILY_TERMS)

    result: dict[str, Any] = model_to_dict(ListingExtraction(platform=platform or detect_platform(url), url=url or UNKNOWN))
    result["platform"] = platform or detect_platform(url)
    result["url"] = url or UNKNOWN

    _extract_from_json_ld(_json_ld_payloads(raw_html or raw), result)

    if result["name"] == UNKNOWN:
        result["name"] = _markdown_title(text)
    if result["name"] == UNKNOWN:
        lines = [line.strip("# *\t ") for line in text.splitlines() if line.strip()]
        result["name"] = next((line for line in lines[:8] if 8 <= len(line) <= 140), UNKNOWN)

    if result["price_total"] == UNKNOWN:
        result["price_total"] = _first_match(
            [
                r"(?:total|gesamt|price|preis)[^\d€]{0,30}€?\s*([0-9][0-9., ]{1,12})",
                r"€\s*([0-9][0-9., ]{1,12})\s*(?:total|gesamt)",
                r"([0-9][0-9., ]{1,12})\s*€\s*(?:total|gesamt)",
            ],
            compact,
        ).rstrip(".")
    result["rating"] = result["rating"] if result["rating"] != UNKNOWN else _first_match([r"([0-9][.,][0-9])\s*(?:/|von|out of)\s*10"], compact)
    result["review_count"] = result["review_count"] if result["review_count"] != UNKNOWN else _first_match([r"([0-9][0-9.]*)\s+(?:reviews|bewertungen|beurteilungen)"], compact)
    result["nights"] = _first_match([r"([0-9]{1,2})\s+(?:nights|nächte|naechte)"], compact)
    result["lat"] = result["lat"] if result["lat"] != UNKNOWN else _first_match([r'"latitude"\s*:\s*"?(-?\d+\.\d+)"?', r"\blat(?:itude)?\b[=: ]+(-?\d+\.\d+)"], combined_raw)
    result["lng"] = result["lng"] if result["lng"] != UNKNOWN else _first_match([r'"longitude"\s*:\s*"?(-?\d+\.\d+)"?', r"\b(?:lng|lon|longitude)\b[=: ]+(-?\d+\.\d+)"], combined_raw)

    result["property_type"] = _infer_property_type(compact)
    result["kitchen"] = _yes_unknown(lower, ["kitchen", "küche", "cocina"])
    result["air_conditioning"] = _yes_unknown(lower, ["air conditioning", "air-conditioned", "klimaanlage", "a/c"])
    result["parking"] = _yes_unknown(lower, ["parking", "parkplatz", "garage"])
    result["terrace_or_balcony"] = _yes_unknown(lower, ["terrace", "balcony", "terraza", "balkon"])
    result["pool_type"] = "private" if "private pool" in lower or "privater pool" in lower else ("shared" if "pool" in lower or "swimming pool" in lower else UNKNOWN)
    result["whole_place_evidence"] = "true" if any(term in lower for term in ["entire home", "entire apartment", "whole place", "gesamte unterkunft"]) else UNKNOWN
    result["family_red_flags"] = "; ".join(hard_terms + soft_terms)
    result["hard_family_red_flags"] = hard_terms
    result["soft_family_red_flags"] = soft_terms
    result["found_terms"] = hard_terms + soft_terms
    result["quiet_evidence"] = "; ".join(term for term in ["quiet", "peaceful", "ruhig", "calm"] if term in lower) or UNKNOWN
    result["review_evidence"] = "review count found" if result["review_count"] != UNKNOWN else UNKNOWN

    return ListingExtraction(**result)


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract structured listing data from crawled markdown/html/text.")
    parser.add_argument("--input", default="", help="Path to raw markdown/html/text. Kept for backwards compatibility.")
    parser.add_argument("--html", default="", help="Path to raw HTML.")
    parser.add_argument("--markdown", default="", help="Path to raw Markdown.")
    parser.add_argument("--url", default="", help="Source URL.")
    parser.add_argument("--platform", default="", help="Known platform.")
    parser.add_argument("--output", default="", help="Optional JSON output path.")
    args = parser.parse_args()

    if not args.input and not args.html and not args.markdown:
        parser.error("one of --input, --html, or --markdown is required")
    raw = Path(args.input).read_text(encoding="utf-8", errors="replace") if args.input else ""
    raw_html = Path(args.html).read_text(encoding="utf-8", errors="replace") if args.html else ""
    raw_markdown = Path(args.markdown).read_text(encoding="utf-8", errors="replace") if args.markdown else ""
    extracted = extract_listing(raw, args.url, args.platform or None, raw_html=raw_html, raw_markdown=raw_markdown)
    payload = model_to_dict(extracted)
    if args.output:
        save_json(Path(args.output), payload)
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
