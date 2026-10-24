"""LangGraph workflow: extract -> market -> score -> discuss <-> score. State persisted per analysis_id."""
import copy
import re
from typing import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt

from . import llm, scoring
from .data import MARKET, ROLE_TITLES, SKILLS
from .extract import RANK, extract_profile
from .models import ChatInterpretation, Summary

# ponytail: in-memory sessions; lost on restart. Run the demo without --reload.
SESSIONS: dict[str, dict] = {}
PROFILE_CACHE: dict[str, dict] = {}  # file hash -> extraction result
MAX_QUESTIONS = 4
CLOSING = "That's everything I wanted to check. Open your plan to see how to close the remaining gaps."


class State(TypedDict, total=False):
    analysis_id: str
    role: str
    file_hash: str
    cv_text: str
    curriculum_text: str
    profile: dict
    projects: list
    experience_months: int
    readiness: int
    previous_readiness: int
    gaps: list
    asked: list
    reply: str
    finished: bool


def _progress(state: State, step: str, message: str):
    s = SESSIONS.get(state["analysis_id"])
    if s and s["status"] == "running":
        s["progress"].append({"step": step, "message": message})


def extract(state: State):
    _progress(state, "cv", "Reading your CV")
    _progress(state, "curriculum", "Reading your curriculum")
    result = PROFILE_CACHE.get(state["file_hash"])
    if result is None:
        result = extract_profile(state["cv_text"], state["curriculum_text"])
        PROFILE_CACHE[state["file_hash"]] = result
    result = copy.deepcopy(result)
    return {"profile": result["profile"], "projects": result["projects"],
            "experience_months": result["experience_months"]}


def market(state: State):
    n = MARKET[state["role"]]["sample_size"]
    _progress(state, "market", f"Analyzing {n} {ROLE_TITLES[state['role']]} postings in Egypt")
    return {}


def score(state: State):
    m = MARKET[state["role"]]
    r = scoring.readiness(state["profile"], m)
    g = scoring.gaps(state["profile"], m)
    _progress(state, "compare", "Comparing your skills")
    _progress(state, "gaps", f"Found {len(g)} gaps")
    return {"previous_readiness": state.get("readiness", r), "readiness": r, "gaps": g}


def _question(gap: dict, role: str) -> str:
    pct = round(gap["frequency"] * 100)
    if gap["user_level"] == "basic":
        return (f"I only see {gap['skill_name']} in your courses, and {pct}% of {ROLE_TITLES[role]} postings ask for it. "
                f"Have you used it in a project?")
    return (f"Your CV doesn't mention {gap['skill_name']}, and {pct}% of {ROLE_TITLES[role]} postings ask for it. "
            f"Have you used it?")


YES = re.compile(r"\b(yes|yeah|yep|sure|i have|i did|used|worked|built)\b|نعم|ايوه|أيوه|اه", re.I)
NO = re.compile(r"\b(no|nope|never|not really|haven't|didn't)\b|لا", re.I)


def _interpret(question: str, answer: str, skill_name: str) -> ChatInterpretation:
    try:
        return llm.structured(
            f"We asked a tech graduate: \"{question}\"\nThey answered: \"{answer}\"\n\n"
            f"Decide whether they have practical experience with {skill_name}.\n"
            "level: basic = only tutorials/course; intermediate = used in a project; strong = used at work; "
            "none = no experience.\nevidence_quote: the part of their answer that supports it (verbatim, short).\n"
            "reply: one short friendly sentence acknowledging the answer. Do not ask a new question.",
            ChatInterpretation, fast=True)
    except llm.LLMError:
        has = bool(YES.search(answer)) and not NO.search(answer)
        return ChatInterpretation(
            has_skill=has, level="intermediate" if has else "none", evidence_quote=answer[:160],
            reply=f"Great, I've added {skill_name} to your profile." if has
            else f"No problem, {skill_name} stays on your plan.")


def discuss(state: State):
    asked = state.get("asked", [])
    candidates = [g for g in state["gaps"] if g["skill_id"] not in asked]
    if not candidates or len(asked) >= MAX_QUESTIONS:
        return {"finished": True, "reply": f"{state.get('reply', '')} {CLOSING}".strip()}

    gap = candidates[0]  # gaps are already ranked: must first, then by frequency
    question = _question(gap, state["role"])
    answer = interrupt(question)  # node re-runs from the top on resume; everything above is deterministic

    sid = gap["skill_id"]
    it = _interpret(question, answer, gap["skill_name"])
    profile = copy.deepcopy(state["profile"])
    entry = profile.setdefault(sid, {"level": "none", "evidence": [], "confirmed": None})
    entry["evidence"].append({"source": "chat", "text": (it.evidence_quote or answer)[:160]})
    if it.has_skill and RANK[it.level] >= RANK["intermediate"]:
        entry["confirmed"] = True
        entry["level"] = it.level if RANK[it.level] > RANK[entry["level"]] else entry["level"]
    elif it.has_skill:  # only tutorials: basic, not confirmed
        entry["level"] = entry["level"] if RANK[entry["level"]] > RANK["basic"] else "basic"
    else:
        entry["confirmed"] = False
    return {"profile": profile, "asked": asked + [sid], "reply": it.reply}


_g = StateGraph(State)
_g.add_node("extract", extract)
_g.add_node("market", market)
_g.add_node("score", score)
_g.add_node("discuss", discuss)
_g.add_edge(START, "extract")
_g.add_edge("extract", "market")
_g.add_edge("market", "score")
_g.add_edge("score", "discuss")
_g.add_conditional_edges("discuss", lambda s: END if s.get("finished") else "score")
GRAPH = _g.compile(checkpointer=InMemorySaver())


def _cfg(aid: str):
    return {"configurable": {"thread_id": aid}}


def state_of(aid: str) -> dict:
    return GRAPH.get_state(_cfg(aid)).values


def _pending(out: dict) -> str | None:
    intr = out.get("__interrupt__")
    return intr[0].value if intr else None


def _summary(st: dict) -> str:
    role = st["role"]
    strong = [SKILLS[s]["name"] for s, e in st["profile"].items() if scoring.match(e) >= 1 and s in SKILLS][:3]
    top = [g["skill_name"] for g in st["gaps"][:3]]
    fallback = (f"You match {st['readiness']}% of what {ROLE_TITLES[role]} postings in Egypt ask for. "
                + (f"Your strongest skills: {', '.join(strong)}. " if strong else "")
                + (f"Biggest gaps: {', '.join(top)}." if top else "No major gaps found."))
    try:
        return llm.structured(
            f"Write a 2-sentence encouraging summary for a fresh grad applying to {ROLE_TITLES[role]} roles. "
            f"Use these facts exactly, do not invent numbers or skills: readiness {st['readiness']}/100; "
            f"strong skills: {strong}; top gaps: {top}.", Summary, fast=True).summary
    except llm.LLMError:
        return fallback


def run_analysis(aid: str, cv_text: str, curriculum_text: str):
    """Runs in a background thread until the first discuss question."""
    s = SESSIONS[aid]
    try:
        out = GRAPH.invoke({"analysis_id": aid, "role": s["role"], "file_hash": s["file_hash"],
                            "cv_text": cv_text, "curriculum_text": curriculum_text}, _cfg(aid))
        s["pending_question"] = _pending(out)
        s["summary"] = _summary(state_of(aid))
        s["status"] = "ready"
        s["progress"].append({"step": "done", "message": "Results ready"})
    except Exception as e:  # surface to the SSE stream instead of dying silently
        s["status"] = "error"
        s["error"] = str(e)
        s["progress"].append({"step": "error", "message": "Analysis failed. Please try again."})


def chat(aid: str, message: str) -> dict:
    s = SESSIONS[aid]
    st = state_of(aid)
    if not message.strip() or not s.get("pending_question"):
        reply = s.get("pending_question") or CLOSING
        return {"reply": reply, "score_changed": False, "previous_readiness": st["readiness"],
                "readiness": st["readiness"], "gaps": st["gaps"]}
    prev = st["readiness"]
    out = GRAPH.invoke(Command(resume=message), _cfg(aid))
    s["pending_question"] = _pending(out)
    reply = out["reply"] if out.get("finished") else f"{out['reply']} {s['pending_question']}"
    return {"reply": reply, "score_changed": out["readiness"] != prev, "previous_readiness": prev,
            "readiness": out["readiness"], "gaps": out["gaps"]}
