"""Skill profile extraction: course map + LLM (grounded) with keyword fallback."""
from rapidfuzz import fuzz

from . import llm
from .data import ALIASES, COURSE_MAP, SKILLS, find_skills, normalize
from .models import ExtractedProfile

RANK = {"none": 0, "basic": 1, "intermediate": 2, "strong": 3}
MAX_EVIDENCE = 4
GROUNDING_THRESHOLD = 85


def _add(profile: dict, sid: str, level: str, evidence: list[dict]):
    entry = profile.setdefault(sid, {"level": "none", "evidence": [], "confirmed": None})
    if RANK[level] > RANK[entry["level"]]:
        entry["level"] = level
    for e in evidence:
        if e not in entry["evidence"] and len(entry["evidence"]) < MAX_EVIDENCE:
            entry["evidence"].append(e)


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


def grounded(quote: str, source: str) -> bool:
    """Anti-hallucination: the evidence quote must fuzzy-match somewhere in the source document."""
    q = _norm(quote)
    return len(q) >= 3 and fuzz.partial_ratio(q, _norm(source)) >= GROUNDING_THRESHOLD


def course_skills(curriculum: str) -> dict:
    """Curriculum lines -> basic skills, via course_skill_map patterns and skill aliases."""
    profile: dict = {}
    for line in curriculum.splitlines():
        low = line.lower().strip()
        if not low:
            continue
        sids = {sid for rx, ids in COURSE_MAP if rx.search(low) for sid in ids} | find_skills(low)
        for sid in sids:
            _add(profile, sid, "basic", [{"source": "course", "text": line.strip()[:160]}])
    return profile


def keyword_skills(cv: str) -> dict:
    # ponytail: fallback when the LLM is down — any CV mention counts as intermediate.
    profile: dict = {}
    for line in cv.splitlines():
        for sid in find_skills(line):
            _add(profile, sid, "intermediate", [{"source": "cv", "text": line.strip()[:160]}])
    return profile


def _prompt(cv: str, curriculum: str) -> str:
    catalog = "\n".join(
        f"- {sid}: {s['name']} (aliases: {', '.join(a for a, i in ALIASES.items() if i == sid)})"
        for sid, s in SKILLS.items())
    return f"""Extract the candidate's technical skill profile from their CV and university curriculum.

Use ONLY these skill ids:
{catalog}

Level rules:
- basic: only seen in a course (curriculum), no project
- intermediate: used in a project (course project, graduation project, personal project)
- strong: used in paid work experience or an internship

Evidence rules:
- Each evidence "text" MUST be a short exact quote (max 20 words) copied verbatim from the document.
- source "cv" for quotes from the CV, "course" for quotes from the curriculum.
- Skip any skill you cannot support with a quote. Do not guess.

Also list the projects from the CV (title + one-line description) and the total months of
work/internship experience (0 if none).

<cv>
{cv}
</cv>

<curriculum>
{curriculum}
</curriculum>"""


def extract_profile(cv: str, curriculum: str) -> dict:
    """-> {"profile": {...}, "projects": [...], "experience_months": int, "extractor": "llm"|"keyword"}"""
    profile = course_skills(curriculum)
    try:
        out: ExtractedProfile = llm.structured(_prompt(cv, curriculum), ExtractedProfile)
    except llm.LLMError:
        for sid, e in keyword_skills(cv).items():
            _add(profile, sid, e["level"], e["evidence"])
        return {"profile": profile, "projects": [], "experience_months": 0, "extractor": "keyword"}

    for s in out.skills:
        sid = normalize(s.skill_id)
        if not sid or s.level == "none":
            continue
        evidence = [e.model_dump() for e in s.evidence
                    if e.source in ("cv", "course") and grounded(e.text, cv if e.source == "cv" else curriculum)]
        if not evidence:
            continue  # hallucinated or unsupported
        level = "basic" if all(e["source"] == "course" for e in evidence) else s.level
        _add(profile, sid, level, evidence)
    return {"profile": profile, "projects": [p.model_dump() for p in out.projects],
            "experience_months": max(0, out.experience_months), "extractor": "llm"}
