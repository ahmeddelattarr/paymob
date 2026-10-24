from typing import Literal

from pydantic import BaseModel

Level = Literal["none", "basic", "intermediate", "strong"]
Tier = Literal["must", "nice", "rare"]


class Evidence(BaseModel):
    source: Literal["cv", "course", "chat"]
    text: str


class Skill(BaseModel):
    skill_id: str
    skill_name: str
    level: Level
    evidence: list[Evidence]


class Gap(BaseModel):
    skill_id: str
    skill_name: str
    tier: Tier
    frequency: float
    user_level: Level
    reason: str


# --- API ---

class AnalyzeResponse(BaseModel):
    analysis_id: str


class ResultsResponse(BaseModel):
    analysis_id: str
    role: str
    role_title: str
    readiness: int
    summary: str
    postings_analyzed: int
    gaps: list[Gap]
    skills: list[Skill]


class ChatRequest(BaseModel):
    message: str = ""


class ChatResponse(BaseModel):
    reply: str
    score_changed: bool
    previous_readiness: int
    readiness: int
    gaps: list[Gap]


class Week(BaseModel):
    week: int
    focus_skills: list[str]
    tasks: list[str]
    hours: int


class Project(BaseModel):
    title: str
    description: str
    skills_covered: list[str]
    milestones: list[str]


class Resource(BaseModel):
    skill_id: str
    title: str
    url: str
    type: str
    language: str
    hours: float
    free: bool


class CareerStep(BaseModel):
    step: int
    title: str
    description: str


class PlanResponse(BaseModel):
    premium: bool
    weeks: list[Week]
    project: Project
    resources: list[Resource]
    projected_readiness: int
    career_path: list[CareerStep]


class RoleScore(BaseModel):
    role: str
    role_title: str
    readiness: int


class CompareResponse(BaseModel):
    roles: list[RoleScore]


class RoleInfo(BaseModel):
    role: str
    role_title: str
    postings_count: int


class RolesResponse(BaseModel):
    roles: list[RoleInfo]


class CheckoutResponse(BaseModel):
    checkout_url: str
    amount_egp: int
    client_secret: str
    public_key: str


class PaymentStatus(BaseModel):
    status: Literal["pending", "paid", "failed"]
    premium: bool


# --- LLM structured outputs ---

class ExtractedSkill(BaseModel):
    skill_id: str
    level: Level
    evidence: list[Evidence]


class ExtractedProject(BaseModel):
    title: str
    description: str


class ExtractedProfile(BaseModel):
    skills: list[ExtractedSkill]
    projects: list[ExtractedProject]
    experience_months: int


class ChatInterpretation(BaseModel):
    has_skill: bool
    level: Level
    evidence_quote: str
    reply: str


class Summary(BaseModel):
    summary: str
