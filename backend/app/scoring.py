"""Deterministic scoring. No LLM, no I/O.

profile: {skill_id: {"level": none|basic|intermediate|strong, "evidence": [...], "confirmed": bool|None}}
market:  {"sample_size": n, "skills": {skill_id: {"frequency": f, "tier": must|nice|rare, "links": [...]}}}
Only must + nice tiers count, for both readiness and gaps.
"""
from .data import SKILLS

LEVEL_MATCH = {"none": 0.0, "basic": 0.5, "intermediate": 1.0, "strong": 1.0}
TIER_ORDER = {"must": 0, "nice": 1}


def match(entry: dict | None) -> float:
    if not entry:
        return 0.0
    if entry.get("confirmed") is True:
        return 1.0
    if entry.get("confirmed") is False:
        return 0.0
    return LEVEL_MATCH[entry["level"]]


def _counted(market: dict):
    return [(sid, m) for sid, m in market["skills"].items() if m["tier"] in TIER_ORDER]


def readiness(profile: dict, market: dict) -> int:
    skills = _counted(market)
    total = sum(m["frequency"] for _, m in skills)
    if not total:
        return 0
    got = sum(m["frequency"] * match(profile.get(sid)) for sid, m in skills)
    return round(100 * got / total)


def _reason(entry: dict | None) -> str:
    if not entry or entry["level"] == "none":
        if entry and entry.get("confirmed") is False:
            return "You said you haven't used it yet"
        return "Not found in your CV or courses"
    sources = {e["source"] for e in entry["evidence"]}
    if "course" in sources and "cv" not in sources:
        return "Only seen in a course, no project"
    return "Only basic experience found"


def gaps(profile: dict, market: dict) -> list[dict]:
    out = []
    for sid, m in _counted(market):
        entry = profile.get(sid)
        if match(entry) >= 1:
            continue
        out.append({
            "skill_id": sid,
            "skill_name": SKILLS.get(sid, {}).get("name", sid),
            "tier": m["tier"],
            "frequency": m["frequency"],
            "user_level": entry["level"] if entry and entry.get("confirmed") is not False else "none",
            "reason": _reason(entry),
        })
    return sorted(out, key=lambda g: (TIER_ORDER[g["tier"]], -g["frequency"], g["skill_id"]))
