"""Plan builder: deterministic weeks/resources/projection; LLM only writes the project (with fallback)."""
import copy

from . import llm, scoring
from .data import MARKET, RESOURCES, ROLE_TITLES, SKILLS
from .models import Project

TOP_GAPS = 5

CAREER_PATHS = {
    "backend": ["Junior Backend Developer", "Backend Developer", "Senior Backend Engineer", "Tech Lead / Architect"],
    "frontend": ["Junior Frontend Developer", "Frontend Developer", "Senior Frontend Engineer", "Frontend Lead / Full-stack"],
    "data_analyst": ["Junior Data Analyst", "Data Analyst", "Senior Analyst / Analytics Engineer", "Analytics Manager / Data Scientist"],
    "ai_ml": ["Junior AI/ML Engineer", "ML Engineer", "Senior ML Engineer", "ML Lead / AI Architect"],
    "qa": ["Junior QA Engineer", "QA Automation Engineer", "Senior SDET", "QA Lead / Engineering Manager"],
    "devops": ["Junior DevOps Engineer", "DevOps Engineer", "Senior DevOps / SRE", "Platform Lead / Cloud Architect"],
}
CAREER_DESCRIPTIONS = [
    "0-2 years: ship features under guidance and learn the team's stack.",
    "2-4 years: own features end to end and make design decisions.",
    "4-7 years: lead system design and mentor juniors.",
    "7+ years: set technical direction across teams.",
]
FALLBACK_PROJECTS = {
    "backend": "Containerized Task Manager API",
    "frontend": "Responsive Job Board Web App",
    "data_analyst": "Egypt Tech Jobs Dashboard",
    "ai_ml": "CV-to-Job Matcher with ML",
    "qa": "Automated Test Suite for a Public Web App",
    "devops": "CI/CD Pipeline for a Dockerized App",
}


def _name(sid):
    return SKILLS.get(sid, {}).get("name", sid)


def pick_resources(sid: str, n: int = 2) -> list[dict]:
    """Prefer free, then Arabic, then shortest."""
    rs = [r for r in RESOURCES if r["skill_id"] == sid]
    return sorted(rs, key=lambda r: (not r["free"], r["language"] != "ar", r["hours"]))[:n]


def _project(role: str, sids: list[str]) -> dict:
    names = [_name(s) for s in sids]
    try:
        p = llm.structured(
            f"Suggest ONE portfolio project for a fresh grad targeting {ROLE_TITLES[role]} roles in Egypt that "
            f"practices as many of these skills as possible: {names}. skills_covered must use these exact ids: {sids}. "
            "Give 4-5 short milestones. Keep it doable in one week.", Project)
        p.skills_covered = [s for s in p.skills_covered if s in sids] or sids
        return p.model_dump()
    except llm.LLMError:
        return {"title": FALLBACK_PROJECTS[role],
                "description": f"A deployable portfolio project that uses {', '.join(names)}, "
                               "documented on GitHub with a clear README.",
                "skills_covered": sids,
                "milestones": [f"Add {n} to the project" for n in names] + ["Deploy it and add the link to your CV"]}


def build(session: dict, state: dict) -> dict:
    role = session["role"]
    top = state["gaps"][:TOP_GAPS]
    sids = [g["skill_id"] for g in top]

    if "project" not in session:  # cache: one LLM call per analysis
        session["project"] = _project(role, sids)
    project = session["project"]

    resources = [r for sid in sids for r in pick_resources(sid)]
    weeks = []
    for w in range(3):
        focus = sids[w::3]
        tasks, hours = [], 0
        for sid in focus:
            res = pick_resources(sid, 1)
            if res:
                tasks.append(f"Study {_name(sid)}: {res[0]['title']} (~{res[0]['hours']:g}h)")
                hours += res[0]["hours"]
            else:
                tasks.append(f"Learn {_name(sid)} fundamentals from the official docs")
                hours += 3
            tasks.append(f"Practice {_name(sid)} in a small exercise and push it to GitHub")
            hours += 3
        if focus:
            weeks.append({"week": w + 1, "focus_skills": focus, "tasks": tasks, "hours": round(hours)})
    weeks.append({"week": len(weeks) + 1, "focus_skills": project["skills_covered"],
                  "tasks": [f"Build: {project['title']}"] + project["milestones"], "hours": 10})

    projected_profile = copy.deepcopy(state["profile"])
    for sid in sids:
        projected_profile[sid] = {"level": "intermediate", "evidence": [], "confirmed": True}

    return {
        "premium": True,
        "weeks": weeks,
        "project": project,
        "resources": resources,
        "projected_readiness": scoring.readiness(projected_profile, MARKET[role]),
        "career_path": [{"step": i + 1, "title": t, "description": CAREER_DESCRIPTIONS[i]}
                        for i, t in enumerate(CAREER_PATHS[role])],
    }


def preview(plan: dict) -> dict:
    """Free tier: week 1 + project title only."""
    return {**plan, "premium": False, "weeks": plan["weeks"][:1],
            "project": {"title": plan["project"]["title"], "description": "", "skills_covered": [], "milestones": []},
            "resources": [], "career_path": []}
