# Career Readiness App (hackathon MVP)

Fresh tech grads in Egypt upload their CV and curriculum, pick a role, and get a readiness score based on real junior job postings. They also get evidence-backed skill gaps, a chat that updates the score live, and a personal plan. The full plan is unlocked with a Paymob payment (test mode).

| Folder | What |
|---|---|
| [`backend/`](backend/) | FastAPI + LangGraph + Gemini + Paymob. Setup: [backend/README.md](backend/README.md) |
| `frontend/` | Next.js app |
| [`shared/`](shared/) | CSV data (skills, course map, job postings, resources) + demo persona PDFs |

## Frontend developers: start here

**[backend/FRONTEND_GUIDE.md](backend/FRONTEND_GUIDE.md)** is the full integration spec: pages to build, user flow, every endpoint with request/response examples, all error codes and messages, the payment flow, TypeScript types, a ready-made API client and a definition-of-done checklist.

Quick start: run the backend (`cd backend && uvicorn app.main:app --port 8000`), then open `http://localhost:8000/docs`. Use `analysis_id = "demo"` to build the UI without uploading anything.
