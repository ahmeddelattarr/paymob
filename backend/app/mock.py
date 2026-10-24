"""Pre-computed result for the demo persona. Served for analysis_id == "demo"."""

DEMO_ID = "demo"

RESULTS = {
    "analysis_id": DEMO_ID,
    "role": "backend",
    "role_title": "Junior Backend Developer",
    "readiness": 62,
    "summary": "You have a solid base in Python, SQL and REST APIs from your courses and graduation project. "
               "The biggest gaps for Egyptian junior backend roles are Docker, Git workflow and testing.",
    "postings_analyzed": 18,
    "gaps": [
        {"skill_id": "docker", "skill_name": "Docker", "tier": "must", "frequency": 0.72, "user_level": "none",
         "reason": "Not found in your CV or courses"},
        {"skill_id": "git", "skill_name": "Git", "tier": "must", "frequency": 0.67, "user_level": "none",
         "reason": "Not found in your CV or courses"},
        {"skill_id": "testing", "skill_name": "Unit Testing", "tier": "nice", "frequency": 0.44, "user_level": "basic",
         "reason": "Only seen in a course, no project"},
        {"skill_id": "redis", "skill_name": "Redis", "tier": "nice", "frequency": 0.28, "user_level": "none",
         "reason": "Not found in your CV or courses"},
    ],
    "skills": [
        {"skill_id": "python", "skill_name": "Python", "level": "intermediate",
         "evidence": [{"source": "cv", "text": "Built a REST API in Python using FastAPI for the graduation project"},
                      {"source": "course", "text": "CS101 Introduction to Programming (Python)"}]},
        {"skill_id": "sql", "skill_name": "SQL", "level": "intermediate",
         "evidence": [{"source": "course", "text": "CS305 Database Systems"},
                      {"source": "cv", "text": "Designed a PostgreSQL schema with 12 tables"}]},
        {"skill_id": "rest_api", "skill_name": "REST APIs", "level": "intermediate",
         "evidence": [{"source": "cv", "text": "Built a REST API in Python using FastAPI for the graduation project"}]},
        {"skill_id": "testing", "skill_name": "Unit Testing", "level": "basic",
         "evidence": [{"source": "course", "text": "CS402 Software Testing"}]},
    ],
}

GAPS_AFTER_GIT = [g for g in RESULTS["gaps"] if g["skill_id"] != "git"]

CHAT_SCRIPT = [
    "Your CV doesn't mention Git, and 67% of junior backend postings ask for it. Have you used Git?",
    "Great, I've added Git to your profile. Your readiness went up. "
    "Next: Docker shows up in 72% of postings. Have you used Docker or containers?",
    "Thanks! That's everything I wanted to check. Head to your plan to close the remaining gaps.",
]

PLAN = {
    "premium": True,
    "weeks": [
        {"week": 1, "focus_skills": ["docker"], "tasks": [
            "Watch 'Docker for Beginners' (Arabic)", "Containerize your graduation project API",
            "Write a docker-compose file with Postgres"], "hours": 8},
        {"week": 2, "focus_skills": ["git"], "tasks": [
            "Learn branching and pull requests", "Push all your projects to GitHub with READMEs"], "hours": 6},
        {"week": 3, "focus_skills": ["testing", "redis"], "tasks": [
            "Add pytest unit tests to your API (70% coverage)", "Add Redis caching to one slow endpoint"], "hours": 8},
        {"week": 4, "focus_skills": ["docker", "testing", "redis"], "tasks": [
            "Build the recommended project end to end", "Deploy it and add the link to your CV"], "hours": 10},
    ],
    "project": {
        "title": "Containerized URL Shortener API",
        "description": "A FastAPI URL shortener with Postgres storage, Redis caching, pytest tests and Docker Compose, "
                       "deployed with a public link.",
        "skills_covered": ["docker", "git", "testing", "redis"],
        "milestones": ["API + Postgres schema", "Redis cache for redirects", "pytest suite", "Docker Compose + deploy"],
    },
    "resources": [
        {"skill_id": "docker", "title": "Docker in Arabic - Full Course", "url": "https://www.youtube.com/results?search_query=docker+arabic",
         "type": "video", "language": "ar", "hours": 4, "free": True},
        {"skill_id": "git", "title": "Pro Git Book", "url": "https://git-scm.com/book/en/v2",
         "type": "docs", "language": "en", "hours": 6, "free": True},
        {"skill_id": "testing", "title": "pytest documentation - Getting Started", "url": "https://docs.pytest.org/en/stable/getting-started.html",
         "type": "docs", "language": "en", "hours": 2, "free": True},
    ],
    "projected_readiness": 91,
    "career_path": [
        {"step": 1, "title": "Junior Backend Developer", "description": "Ship features and fix bugs under guidance (0-2 yrs)."},
        {"step": 2, "title": "Backend Developer", "description": "Own services end to end, design APIs and schemas (2-4 yrs)."},
        {"step": 3, "title": "Senior Backend Engineer", "description": "Lead system design, mentor juniors (4-7 yrs)."},
        {"step": 4, "title": "Tech Lead / Software Architect", "description": "Set technical direction across teams."},
    ],
}

COMPARE = {"roles": [
    {"role": "backend", "role_title": "Junior Backend Developer", "readiness": 62},
    {"role": "data_analyst", "role_title": "Junior Data Analyst", "readiness": 48},
    {"role": "ai_ml", "role_title": "Junior AI/ML Engineer", "readiness": 41},
    {"role": "qa", "role_title": "Junior QA Engineer", "readiness": 39},
    {"role": "devops", "role_title": "Junior DevOps Engineer", "readiness": 27},
    {"role": "frontend", "role_title": "Junior Frontend Developer", "readiness": 22},
]}

STREAM_STEPS = [
    ("cv", "Reading your CV"),
    ("curriculum", "Reading your curriculum"),
    ("market", "Analyzing 18 Junior Backend postings in Egypt"),
    ("compare", "Comparing your skills"),
    ("gaps", "Found 4 gaps"),
]
