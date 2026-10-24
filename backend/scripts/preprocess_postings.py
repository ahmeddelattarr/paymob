"""One-time: extract required skills from every posting with the LLM -> shared/market_demand.json.

Run from backend/:  python -m scripts.preprocess_postings
Postings the LLM fails on fall back to keyword matching, so the file is always complete.
"""
import json
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel

from app import llm
from app.config import SHARED_DIR
from app.data import POSTINGS, SKILLS, compute_market, find_skills, normalize


class PostingSkills(BaseModel):
    skill_ids: list[str]


CATALOG = ", ".join(f"{sid} ({s['name']})" for sid, s in SKILLS.items())


def skills_for(posting: dict) -> set[str]:
    try:
        out = llm.structured(
            f"List the technical skills this junior job posting asks for (required or nice-to-have). "
            f"Use ONLY these skill ids: {CATALOG}\n\n"
            f"Title: {posting['job_title']}\n{posting['description']}", PostingSkills, fast=True)
        found = {normalize(s) for s in out.skill_ids} - {None}
        return found or find_skills(posting["description"])
    except llm.LLMError as e:
        print(f"  fallback (keyword) for {posting['link']}: {e}")
        return find_skills(posting["job_title"] + " " + posting["description"])


if __name__ == "__main__":
    with ThreadPoolExecutor(8) as pool:
        skills = list(pool.map(skills_for, POSTINGS))
    market = compute_market(list(zip(POSTINGS, skills)))
    path = SHARED_DIR / "market_demand.json"
    path.write_text(json.dumps(market, indent=2), encoding="utf-8")
    print(f"wrote {path}: " + ", ".join(f"{r}={m['sample_size']}" for r, m in market.items()))
