from __future__ import annotations

import argparse
import html as html_lib
import json
import re
from pathlib import Path
from typing import Any, Iterable

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from utils import UNKNOWN, detect_platform, is_unknownish, save_json

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
    "outdoor play equipment",
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
    "kids",
    "toddler",
    "baby",
    "kinder",
    "familie",
    "familienfreundlich",
    "treppenschutz",
    "brettspiele",
    "puzzle",
    "board games",
    "puzzles",
    "wasserspielzeug",
    "water toys",
    "family-friendly",
]

AMENITY_TERMS = {
    "kitchen": ["kitchen", "küche", "kueche", "cocina", "kochnische"],
    "air_conditioning": ["air conditioning", "air-conditioned", "klimaanlage", "klimatisiert", "a/c", "ac ", "aire acondicionado"],
    "parking": ["parking", "parkplatz", "garage", "free parking", "kostenloser parkplatz", "aparcamiento"],
    "terrace_or_balcony": ["terrace", "balcony", "terraza", "balkon", "terrasse", "patio"],
}

QUIET_TERMS = ["quiet", "peaceful", "ruhig", "calm", "tranquil", "tranquilo", "entspannen", "relax"]
POOL_PRIVATE_TERMS = ["private pool", "privater pool", "eigener pool", "piscina privada"]
POOL_SHARED_TERMS = ["shared pool", "gemeinschaftspool", "gemeinschafts pool", "pool", "swimming pool", "piscina"]
WHOLE_PLACE_TERMS = [
    "entire home",
    "entire apartment",
    "whole place",
    "gesamte unterkunft",
    "gesamte wohnung",
    "gesamtes apartment",
    "gesamtes ferienhaus",
    "vivienda completa",
]

TITLE_KEYS = {
    "title",
    "name",
    "localizedtitle",
    "listingtitle",
    "pdptitle",
    "roomtitle",
    "hometitle",
}
LOCATION_KEYS = {
    "location",
    "locationtitle",
    "localizedcityname",
    "city",
    "publicaddress",
    "address",
    "addresslocality",
    "localizedlocation",
    "maplabel",
}
RATING_KEYS = {"rating", "avgrating", "starrating", "guestrating", "ratingvalue", "localizedrating"}
REVIEW_KEYS = {"reviewcount", "reviewscount", "visiblereviewcount", "reviewcountlocalized", "localizedreviewcount"}
LAT_KEYS = {"lat", "latitude"}
LNG_KEYS = {"lng", "lon", "long", "longitude"}
PRICE_KEYS = {"price", "amount", "total", "totalprice", "localizedtotalprice", "displayprice", "priceamount"}

BAD_TITLE_PARTS = [
    "airbnb",
    "unterkünfte",
    "erlebnisse",
    "services",
    "hilfe-center",
    "werde gastgeber",
    "einloggen",
    "registrieren",
    "suche starten",
    "standort",
    "check-in",
    "check-out",
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
    if "<html" in text.lower() or "<body" in text.lower() or "<script" in text.lower():
        soup = BeautifulSoup(text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text("\n")
    text = html_lib.unescape(text)
    return re.sub(r"[ \t]+", " ", text).strip()


def _safe_json_loads(text: str) -> Any | None:
    text = html_lib.unescape(text or "").strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return None


def _balanced_fragment(text: str, start: int, max_chars: int = 2_500_000) -> str:
    if start < 0 or start >= len(text) or text[start] not in "[{":
        return ""
    opener = text[start]
    closer = "}" if opener == "{" else "]"
    depth = 0
    in_string = False
    quote = ""
    escaped = False
    end_limit = min(len(text), start + max_chars)
    for idx in range(start, end_limit):
        char = text[idx]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                in_string = False
            continue
        if char in {'"', "'"}:
            in_string = True
            quote = char
            continue
        if char == opener:
            depth += 1
        elif char == closer:
            depth -= 1
            if depth == 0:
                return text[start : idx + 1]
    return ""


def _json_payloads_from_script_text(script_text: str) -> list[Any]:
    payloads: list[Any] = []
    text = html_lib.unescape(script_text or "")
    direct = _safe_json_loads(text)
    if direct is not None:
        payloads.append(direct)
        return payloads

    starts = [m.start(1) for m in re.finditer(r"(?:=|:)\s*([\[{])", text)]
    # Airbnb frequently stores JSON in large app-state scripts. Keep the scan bounded.
    for start in starts[:40]:
        fragment = _balanced_fragment(text, start)
        if not fragment:
            continue
        parsed = _safe_json_loads(fragment)
        if parsed is not None:
            payloads.append(parsed)
    return payloads


def _json_payloads(raw_html: str) -> list[Any]:
    soup = BeautifulSoup(raw_html or "", "html.parser")
    payloads: list[Any] = []
    for script in soup.find_all("script"):
        script_text = script.get_text("", strip=False)
        script_type = str(script.get("type") or "").lower()
        script_id = str(script.get("id") or "").lower()
        if not script_text:
            continue
        if "json" in script_type or script_id in {"__next_data__", "data-deferred-state"}:
            parsed = _safe_json_loads(script_text)
            if parsed is not None:
                payloads.append(parsed)
                continue
        if any(marker in script_text.lower() for marker in ["airbnb", "niobeminimalclientdata", "stayspdp", "listing", "room"]):
            payloads.extend(_json_payloads_from_script_text(script_text))
    return payloads


def _flatten_payloads(payloads: list[Any]) -> list[dict[str, Any]]:
    flat: list[dict[str, Any]] = []
    for payload in payloads:
        for item in _walk(payload):
            if isinstance(item, dict):
                flat.append(item)
    return flat


def _walk(value: Any, limit: int = 80_000) -> Iterable[Any]:
    seen = 0
    stack = [value]
    while stack and seen < limit:
        current = stack.pop()
        seen += 1
        yield current
        if isinstance(current, dict):
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)


def _collect_string_values(payloads: list[Any], limit: int = 4_000) -> list[str]:
    strings: list[str] = []
    for payload in payloads:
        for item in _walk(payload):
            if isinstance(item, str):
                text = html_lib.unescape(item).strip()
                if 2 <= len(text) <= 300:
                    strings.append(text)
                    if len(strings) >= limit:
                        return strings
    return strings


def _json_ld_payloads(raw: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(raw or "", "html.parser")
    payloads: list[dict[str, Any]] = []
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        parsed = _safe_json_loads(script.get_text(strip=True))
        if parsed is None:
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
            if _looks_like_listing_title(title):
                return title
    return UNKNOWN


def _looks_like_listing_title(value: Any) -> bool:
    text = str(value or "").strip()
    text_l = text.lower()
    if not (5 <= len(text) <= 160):
        return False
    if any(part in text_l for part in BAD_TITLE_PARTS):
        return False
    if re.fullmatch(r"[0-9., €]+", text):
        return False
    return True


def _looks_like_location(value: Any) -> bool:
    text = str(value or "").strip()
    if not (2 <= len(text) <= 180):
        return False
    text_l = text.lower()
    if any(part in text_l for part in ["check-in", "check-out", "bewertung", "reviews", "hilfe", "airbnb"]):
        return False
    return True


def _contains_any(text: str, terms: list[str]) -> list[str]:
    text_l = text.lower()
    return [term for term in terms if term in text_l]


def _yes_unknown(text: str, terms: list[str]) -> str:
    return "true" if _contains_any(text, terms) else UNKNOWN


def _infer_property_type(text: str) -> str:
    checks = [
        ("villa", ["villa"]),
        ("holiday home", ["holiday home", "ferienhaus", "casa", "house"]),
        ("bungalow", ["bungalow"]),
        ("apartment", ["apartment", "apartamento", "wohnung", "flat", "ferienwohnung"]),
        ("hotel", ["hotel"]),
        ("aparthotel", ["aparthotel"]),
        ("room", ["private room", "zimmer"]),
    ]
    text_l = text.lower()
    for label, terms in checks:
        if any(term in text_l for term in terms):
            return label
    return UNKNOWN


def _set_if_unknown(result: dict[str, Any], key: str, value: Any) -> None:
    if not is_unknownish(result.get(key)):
        return
    if value is None:
        return
    text = html_lib.unescape(str(value)).strip()
    if text and not is_unknownish(text):
        result[key] = text


def _numeric_string(value: Any) -> str:
    if value is None:
        return UNKNOWN
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value).strip()
    match = re.search(r"-?\d+(?:[.,]\d+)?", text.replace(" ", ""))
    return match.group(0).replace(",", ".") if match else UNKNOWN


def _extract_from_json_ld(payloads: list[dict[str, Any]], result: dict[str, Any]) -> None:
    for payload in payloads:
        if result["name"] == UNKNOWN and payload.get("name") and _looks_like_listing_title(payload.get("name")):
            result["name"] = str(payload["name"])
        address = payload.get("address")
        if result["location"] == UNKNOWN:
            if isinstance(address, dict):
                location = ", ".join(str(address.get(k, "")) for k in ["addressLocality", "addressRegion", "addressCountry"] if address.get(k))
                if _looks_like_location(location):
                    result["location"] = location
            elif isinstance(address, str) and _looks_like_location(address):
                result["location"] = address
        geo = payload.get("geo")
        if isinstance(geo, dict):
            _set_if_unknown(result, "lat", geo.get("latitude"))
            _set_if_unknown(result, "lng", geo.get("longitude"))
        aggregate = payload.get("aggregateRating")
        if isinstance(aggregate, dict):
            _set_if_unknown(result, "rating", aggregate.get("ratingValue"))
            _set_if_unknown(result, "review_count", aggregate.get("reviewCount"))
        offers = payload.get("offers")
        if isinstance(offers, dict):
            _set_if_unknown(result, "price_total", offers.get("price"))


def _extract_from_nested_json(payloads: list[Any], result: dict[str, Any]) -> None:
    for node in _flatten_payloads(payloads):
        lowered = {str(k).lower().replace("_", "").replace("-", ""): v for k, v in node.items()}

        for key in TITLE_KEYS:
            value = lowered.get(key)
            if result["name"] == UNKNOWN and isinstance(value, str) and _looks_like_listing_title(value):
                result["name"] = value.strip()

        for key in LOCATION_KEYS:
            value = lowered.get(key)
            if result["location"] == UNKNOWN:
                if isinstance(value, str) and _looks_like_location(value):
                    result["location"] = value.strip()
                elif isinstance(value, dict):
                    parts = [str(value.get(part, "")).strip() for part in ["city", "addressLocality", "state", "country"] if value.get(part)]
                    joined = ", ".join(parts)
                    if _looks_like_location(joined):
                        result["location"] = joined

        for key in LAT_KEYS:
            if result["lat"] == UNKNOWN and key in lowered:
                candidate = _numeric_string(lowered[key])
                if candidate != UNKNOWN:
                    result["lat"] = candidate
        for key in LNG_KEYS:
            if result["lng"] == UNKNOWN and key in lowered:
                candidate = _numeric_string(lowered[key])
                if candidate != UNKNOWN:
                    result["lng"] = candidate

        for key in RATING_KEYS:
            if result["rating"] == UNKNOWN and key in lowered:
                candidate = _numeric_string(lowered[key])
                if candidate != UNKNOWN:
                    result["rating"] = candidate
        for key in REVIEW_KEYS:
            if result["review_count"] == UNKNOWN and key in lowered:
                candidate = _numeric_string(lowered[key])
                if candidate != UNKNOWN:
                    result["review_count"] = candidate

        if result["price_total"] == UNKNOWN:
            for key, value in lowered.items():
                key_has_price_signal = key in PRICE_KEYS or ("price" in key and any(part in key for part in ["total", "display", "amount"]))
                if not key_has_price_signal:
                    continue
                candidate = _numeric_string(value)
                if candidate != UNKNOWN:
                    result["price_total"] = candidate
                    break


def _extract_regex_fields(compact: str, combined_raw: str, result: dict[str, Any]) -> None:
    if result["price_total"] == UNKNOWN:
        result["price_total"] = _first_match(
            [
                r"(?:total|gesamt|price|preis|summe)[^\d€]{0,40}€?\s*([0-9][0-9., ]{1,12})",
                r"€\s*([0-9][0-9., ]{1,12})\s*(?:total|gesamt|summe)",
                r"([0-9][0-9., ]{1,12})\s*€\s*(?:total|gesamt|summe)",
            ],
            compact,
        ).rstrip(".")
    if result["rating"] == UNKNOWN:
        result["rating"] = _first_match(
            [
                r"([0-9][.,][0-9])\s*(?:/|von|out of)\s*5",
                r"([0-9][.,][0-9])\s*(?:/|von|out of)\s*10",
            ],
            compact,
        )
    if result["review_count"] == UNKNOWN:
        result["review_count"] = _first_match([r"([0-9][0-9.]*)\s+(?:reviews|bewertungen|beurteilungen)", r"([0-9][0-9.]*)\s*Bewertung"], compact)
    if result["nights"] == UNKNOWN:
        result["nights"] = _first_match([r"([0-9]{1,2})\s+(?:nights|nächte|naechte|Nächte|Nacht)", r"für\s+([0-9]{1,2})\s+Nächte"], compact)
    if result["lat"] == UNKNOWN:
        result["lat"] = _first_match([r'"latitude"\s*:\s*"?(-?\d+\.\d+)"?', r"\blat(?:itude)?\b[=: ]+(-?\d+\.\d+)"], combined_raw)
    if result["lng"] == UNKNOWN:
        result["lng"] = _first_match([r'"longitude"\s*:\s*"?(-?\d+\.\d+)"?', r"\b(?:lng|lon|longitude)\b[=: ]+(-?\d+\.\d+)"], combined_raw)
    if result["location"] == UNKNOWN:
        location = _first_match(
            [
                r"(?:Apartment|Wohnung|Unterkunft|Ferienwohnung|Ferienhaus|Villa)\s+(?:in|bei)\s+([^\n·|]{3,100})",
                r"in\s+([A-ZÄÖÜ][A-Za-zÀ-ÿ' .-]{2,70}),\s*(?:Spanien|Spain)",
            ],
            compact,
        )
        if _looks_like_location(location):
            result["location"] = location


def extract_listing(
    raw: str = "",
    url: str = "",
    platform: str | None = None,
    raw_html: str = "",
    raw_markdown: str = "",
) -> ListingExtraction:
    if raw and not raw_html and not raw_markdown:
        if "<html" in raw.lower() or "<body" in raw.lower() or "<script" in raw.lower():
            raw_html = raw
        else:
            raw_markdown = raw

    combined_raw = "\n".join(part for part in [raw_html, raw_markdown] if part)
    json_payloads = _json_payloads(raw_html or raw)
    json_ld_payloads = _json_ld_payloads(raw_html or raw)
    json_strings = _collect_string_values(json_payloads)

    text = _clean_text(combined_raw)
    compact = re.sub(r"\s+", " ", text)
    json_text = "\n".join(json_strings)
    analysis_text = f"{compact}\n{json_text}"
    lower = analysis_text.lower()

    hard_terms = _contains_any(analysis_text, HARD_FAMILY_TERMS)
    soft_terms = _contains_any(analysis_text, SOFT_FAMILY_TERMS)

    result: dict[str, Any] = model_to_dict(ListingExtraction(platform=platform or detect_platform(url), url=url or UNKNOWN))
    result["platform"] = platform or detect_platform(url)
    result["url"] = url or UNKNOWN

    _extract_from_json_ld(json_ld_payloads, result)
    _extract_from_nested_json(json_payloads, result)

    if result["name"] == UNKNOWN:
        result["name"] = _markdown_title(text)
    if result["name"] == UNKNOWN:
        lines = [line.strip("# *\t ") for line in text.splitlines() if line.strip()]
        result["name"] = next((line for line in lines[:15] if _looks_like_listing_title(line)), UNKNOWN)

    _extract_regex_fields(analysis_text, combined_raw, result)

    if result["property_type"] == UNKNOWN:
        result["property_type"] = _infer_property_type(analysis_text)

    result["kitchen"] = _yes_unknown(lower, AMENITY_TERMS["kitchen"])
    result["air_conditioning"] = _yes_unknown(lower, AMENITY_TERMS["air_conditioning"])
    result["parking"] = _yes_unknown(lower, AMENITY_TERMS["parking"])
    result["terrace_or_balcony"] = _yes_unknown(lower, AMENITY_TERMS["terrace_or_balcony"])

    if any(term in lower for term in POOL_PRIVATE_TERMS):
        result["pool_type"] = "private"
    elif any(term in lower for term in POOL_SHARED_TERMS):
        result["pool_type"] = "shared"

    result["whole_place_evidence"] = "true" if any(term in lower for term in WHOLE_PLACE_TERMS) else UNKNOWN
    result["family_red_flags"] = "; ".join(hard_terms + soft_terms)
    result["hard_family_red_flags"] = hard_terms
    result["soft_family_red_flags"] = soft_terms
    result["found_terms"] = hard_terms + soft_terms

    quiet_terms = [term for term in QUIET_TERMS if term in lower]
    result["quiet_evidence"] = "; ".join(quiet_terms) if quiet_terms else UNKNOWN
    result["review_evidence"] = f"{result['review_count']} Bewertungen gefunden" if result["review_count"] != UNKNOWN else UNKNOWN

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
