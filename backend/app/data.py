"""CSV data loaded once at import: skills, aliases, course map, postings, resources, market demand."""
import csv
import json
import re

from .config import SHARED_DIR

ROLE_TITLES = {
    "backend": "Junior Backend Developer",
    "frontend": "Junior Frontend Developer",
    "data_analyst": "Junior Data Analyst",
    "ai_ml": "Junior AI/ML Engineer",
    "qa": "Junior QA Engineer",
    "devops": "Junior DevOps Engineer",
}


def _rows(name):
    with open(SHARED_DIR / name, encoding="utf-8") as f:
        return [{k.strip(): (v or "").strip() for k, v in row.items()} for row in csv.DictReader(f)]


def _word_re(phrase):
    return re.compile(r"(?<!\w)" + re.escape(phrase.lower()) + r"(?!\w)")


SKILLS = {r["skill_id"]: {"name": r["canonical_name"], "category": r["category"]} for r in _rows("skills.csv")}

ALIASES: dict[str, str] = {}  # lowercase alias / id / name -> skill_id
for _r in _rows("skills.csv"):
    for _a in [_r["skill_id"], _r["canonical_name"], *_r["aliases"].split("|")]:
        if _a.strip():
            ALIASES.setdefault(_a.strip().lower(), _r["skill_id"])
_ALIAS_RES = [(_word_re(a), sid) for a, sid in ALIASES.items()]

COURSE_MAP = [(_word_re(r["course_name_pattern"]), [s for s in r["skill_ids"].split("|") if s in SKILLS])
              for r in _rows("course_skill_map.csv")]

POSTINGS = _rows("job_postings.csv")
RESOURCES = [{**r, "hours": float(r["hours"] or 0), "free": r["free"].lower() == "true"}
             for r in _rows("resources.csv")]


def normalize(name: str) -> str | None:
    """Map any skill name / alias / id to its canonical skill_id, or None if unknown."""
    key = name.strip().lower()
    return ALIASES.get(key) or ALIASES.get(key.replace("_", " "))


def find_skills(text: str) -> set[str]:
    """Skill ids whose aliases appear as whole words in text."""
    low = text.lower()
    return {sid for rx, sid in _ALIAS_RES if rx.search(low)}


def tier(freq: float) -> str:
    return "must" if freq >= 0.5 else "nice" if freq >= 0.2 else "rare"


def compute_market(posting_skills: list[tuple[dict, set[str]]]) -> dict:
    """posting_skills: [(posting_row, skill_ids)] -> {role: {sample_size, skills: {id: {frequency, tier, links}}}}"""
    market = {}
    for role in ROLE_TITLES:
        rows = [(p, s) for p, s in posting_skills if p["role"] == role]
        counts: dict[str, list[str]] = {}
        for p, skills in rows:
            for sid in skills:
                counts.setdefault(sid, []).append(p["link"])
        skills = {}
        for sid, links in counts.items():
            f = round(len(links) / len(rows), 2)
            skills[sid] = {"frequency": f, "tier": tier(f), "links": links[:3]}
        market[role] = {"sample_size": len(rows), "skills": skills}
    return market


def _load_market():
    path = SHARED_DIR / "market_demand.json"
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8")), "file"
    # Fallback: keyword matching over postings (deterministic, no LLM).
    return compute_market([(p, find_skills(p["description"])) for p in POSTINGS]), "keyword_fallback"


MARKET, MARKET_SOURCE = _load_market()
