from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

from utils import UNKNOWN, as_bool, clamp, fmt_number, parse_float, parse_int, save_json

ALC = (38.2822, -0.5582)
VLC = (39.4893, -0.4816)

GOOD_BEACH_AREAS = [
    "cala moraig",
    "cala dels testos",
    "cala llebeig",
    "cala baladrar",
    "cala advocat",
    "la solsida",
    "cala llobella",
    "cala pinets",
    "cala del portitxol",
    "granadella",
    "la solsida",
    "racó del conill",
    "raco del conill",
    "cala del racó del corb",
    "cala mascarat",
    "cumbre",
    "benitatxell",
    "benitachell",
    "moraira",
    "benissa costa",
    "cala baladrar",
    "cala advocat",
    "altea cap negret",
    "cap negret",
    "el portet",
    "altea-mascarat",
    "mascarat",
]

BAD_BEACH_AREAS = [
    "benidorm",
    "levante",
    "rincon de loix",
    "rincón de loix",
    "calpe la fossa",
    "la fossa",
    "calpe city centre",
    "jávea arenal",
    "javea arenal",
    "cala finestrat beachfront",
    "promenade",
    "promenade beach",
    "resort",
    "aparthotel",
]

HARD_EXCLUDE_TERMS = [
    "familienzimmer",
    "family rooms",
    "kinderbecken",
    "kids pool",
    "children pool",
    "kinderspielplatz",
    "playground",
    "spielzimmer",
    "game room",
    "indoorspielbereich",
    "outdoorspielgeräte",
    "outdoorspielgeraete",
    "aparthotel",
    "resort",
    "aqua park",
    "wasserpark",
    "kids club",
    "kinderclub",
    "entertainment team",
    "animation",
]


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lng2 - lng1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return 2 * radius * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def road_distance(lat: float | None, lng: float | None, airport: tuple[float, float]) -> tuple[float | None, float | None]:
    if lat is None or lng is None:
        return None, None
    road_km = haversine_km(lat, lng, airport[0], airport[1]) * 1.23
    drive_min = road_km / 75 * 60
    return road_km, drive_min


def budget_score(price_per_person: float | None) -> float:
    if price_per_person is None:
        return 0
    if price_per_person <= 350:
        return 10
    if price_per_person <= 400:
        return 9
    if price_per_person <= 450:
        return 8
    if price_per_person <= 500:
        return 7
    if price_per_person <= 550:
        return 5
    if price_per_person <= 650:
        return 3
    return 1


def existing_score(data: dict[str, Any], key: str, fallback: float) -> float:
    value = parse_float(data.get(key))
    return fallback if value is None else value


def score_private_level(data: dict[str, Any]) -> float:
    text = " ".join(str(data.get(k, "")) for k in ["property_type", "whole_place_evidence", "name"]).lower()
    if "hotel" in text or "room" in text:
        return 2
    if "villa" in text or "holiday home" in text or "bungalow" in text:
        return 8
    if "entire" in text or "whole" in text or as_bool(data.get("whole_place_evidence")):
        return 7
    if "apartment" in text:
        return 5.5
    return 5


def child_potential(data: dict[str, Any]) -> float:
    flags = str(data.get("family_red_flags", "")).lower()
    hard_hits = [term for term in HARD_EXCLUDE_TERMS if term in flags]
    if hard_hits:
        return 10
    soft_hits = len([term for term in ["children", "child", "baby", "board games", "puzzles", "family-friendly"] if term in flags])
    base = 1.5 + min(soft_hits * 2.0, 6)
    pool = str(data.get("pool_type", "")).lower()
    if pool == "shared":
        base += 1.0
    property_type = str(data.get("property_type", "")).lower()
    if "hotel" in property_type or "aparthotel" in property_type or "resort" in flags:
        base += 2.5
    return clamp(base)


def review_evidence_score(data: dict[str, Any]) -> float:
    count = parse_int(data.get("review_count"))
    quiet = str(data.get("quiet_evidence", "")).lower()
    if count is None:
        score = 1
    elif count >= 50:
        score = 8
    elif count >= 10:
        score = 5
    elif count >= 1:
        score = 3
    else:
        score = 1
    if any(term in quiet for term in ["quiet", "peaceful", "ruhig", "calm"]):
        score += 1.5
    return clamp(score)


def beach_fit_score(data: dict[str, Any]) -> float:
    text = " ".join(str(data.get(k, "")) for k in ["location", "name", "notes"]).lower()
    if any(area in text for area in GOOD_BEACH_AREAS):
        return 8.5
    if any(area in text for area in BAD_BEACH_AREAS):
        return 3
    if any(term in text for term in ["tarbena", "inland", "beniarbeig"]):
        return 2.5
    if any(term in text for term in ["calp", "calpe", "altea", "benissa", "javea", "jávea"]):
        return 6
    return 4


def transfer_score(alc_km: float | None, vlc_km: float | None) -> float:
    distance = alc_km if alc_km is not None else vlc_km
    if distance is None:
        return 4
    if distance <= 70:
        return 9
    if distance <= 90:
        return 7.5
    if distance <= 110:
        return 5.5
    if distance <= 140:
        return 4
    return 2


def quiet_score(data: dict[str, Any], child_score: float) -> float:
    score = 6.0
    text = " ".join(str(data.get(k, "")) for k in ["location", "property_type", "quiet_evidence", "family_red_flags", "name"]).lower()
    if any(term in text for term in ["quiet", "peaceful", "ruhig", "calm", "cumbre", "benitatxell", "benitachell", "tárbena", "tarbena"]):
        score += 2
    if any(term in text for term in ["benidorm", "levante", "arenal", "promenade", "resort", "aparthotel", "animation"]):
        score -= 3
    if str(data.get("pool_type", "")).lower() == "shared":
        score -= 0.8
    score -= max(0, child_score - 4) * 0.35
    return clamp(score)


def score_candidate(data: dict[str, Any]) -> dict[str, Any]:
    scored = dict(data)
    price_total = parse_float(scored.get("price_total"))
    nights = parse_int(scored.get("nights"))
    price_pp = price_total / 2 if price_total is not None else None
    price_pppn = price_pp / nights if price_pp is not None and nights else None

    scored["price_per_person"] = fmt_number(price_pp, 2) if price_pp is not None else UNKNOWN
    scored["price_per_person_per_night"] = fmt_number(price_pppn, 2) if price_pppn is not None else UNKNOWN
    scored["budget_under_500pp"] = "true" if price_pp is not None and price_pp <= 500 else ("false" if price_pp is not None else UNKNOWN)

    lat = parse_float(scored.get("lat"))
    lng = parse_float(scored.get("lng"))
    alc_km, alc_min = road_distance(lat, lng, ALC)
    vlc_km, vlc_min = road_distance(lat, lng, VLC)
    scored["alc_km_est"] = fmt_number(alc_km, 1)
    scored["alc_drive_min_est"] = fmt_number(alc_min, 0)
    scored["vlc_km_est"] = fmt_number(vlc_km, 1)
    scored["vlc_drive_min_est"] = fmt_number(vlc_min, 0)
    scored["airport_distance_method"] = "coordinate approximation, not live Google Maps" if lat is not None and lng is not None else UNKNOWN

    private = existing_score(scored, "private_level", score_private_level(scored))
    child = existing_score(scored, "child_potential_0_10", child_potential(scored))
    review_score = existing_score(scored, "review_evidence_0_10", review_evidence_score(scored))
    beach = existing_score(scored, "beach_fit_0_10", beach_fit_score(scored))
    transfer = existing_score(scored, "transfer_score_0_10", transfer_score(alc_km, vlc_km))
    budget = budget_score(price_pp)
    quiet = existing_score(scored, "quiet_score_0_10", quiet_score(scored, child))

    family_flags = str(scored.get("family_red_flags", "")).lower()
    hard_excluded = any(term in family_flags for term in HARD_EXCLUDE_TERMS)
    excluded = as_bool(scored.get("excluded")) or hard_excluded
    if hard_excluded and not scored.get("exclusion_reason"):
        scored["exclusion_reason"] = "family_no_go"
    if excluded and str(scored.get("exclusion_reason", "")).strip().lower() in {"", "none", "unknown"}:
        scored["exclusion_reason"] = "excluded"

    overall = (
        private * 0.18
        + (10 - child) * 0.18
        + quiet * 0.18
        + beach * 0.14
        + transfer * 0.10
        + budget * 0.12
        + review_score * 0.10
    )
    if excluded:
        overall = 0

    scored.update(
        {
            "private_level": fmt_number(clamp(private), 1),
            "child_potential_0_10": fmt_number(clamp(child), 1),
            "quiet_score_0_10": fmt_number(clamp(quiet), 1),
            "review_evidence_0_10": fmt_number(clamp(review_score), 1),
            "beach_fit_0_10": fmt_number(clamp(beach), 1),
            "transfer_score_0_10": fmt_number(clamp(transfer), 1),
            "budget_score_0_10": fmt_number(clamp(budget), 1),
            "overall_score_0_10": fmt_number(clamp(overall), 2),
            "excluded": "true" if excluded else "false",
        }
    )
    return scored


def main() -> int:
    parser = argparse.ArgumentParser(description="Score one extracted travel candidate JSON file.")
    parser.add_argument("--input", required=True)
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    data = json.loads(Path(args.input).read_text(encoding="utf-8"))
    scored = score_candidate(data)
    if args.output:
        save_json(Path(args.output), scored)
    else:
        print(json.dumps(scored, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
