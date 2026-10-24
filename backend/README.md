# Career Readiness API (backend)

FastAPI + LangGraph + Claude. Reads a CV and a curriculum PDF, scores readiness against Egyptian junior job postings, runs a chat that rescores live, builds a plan, and unlocks the premium plan through a Paymob test payment.

## Setup

```bash
cd backend
python -m venv .venv
.venv/Scripts/activate          # Windows;  source .venv/bin/activate on macOS/Linux
pip install -r requirements.txt
cp .env.example .env            # fill in ANTHROPIC_API_KEY and the Paymob TEST keys
uvicorn app.main:app --port 8000
```

Don't use `--reload` during the demo. Sessions and payment status live in memory, so every reload wipes them.

- Health: `GET http://localhost:8000/health` (add `?llm_check=true` to make one real LLM call)
- Docs: `http://localhost:8000/docs`
- Tests: `python -m pytest -q`

## Demo safety

- **`analysis_id = demo`**: `/results`, `/stream`, `/chat`, `/plan` and `/roles/compare` serve a precomputed persona instantly, with no upload and no LLM. Payments work for it too.
- **Demo PDFs**: `shared/demo/demo_cv.pdf` and `demo_curriculum.pdf`. Regenerate them with `python scripts/make_demo_pdfs.py`.
- **No LLM key, or the LLM is down?** Every LLM call has a deterministic fallback:
  - skills: keyword plus course-map matching
  - chat: yes/no parsing
  - summary and project: templates

  The app keeps working.
- **Cache**: the skill profile is cached by the SHA-256 of both files, so re-uploading the same files skips the LLM and gives the same score.

## Market data

- At runtime the API reads `shared/market_demand.json`. If that file is missing, it computes demand from `job_postings.csv` with alias keyword matching.
- To build the file with the LLM after new postings arrive, run `python -m scripts.preprocess_postings` from `backend/`, then restart.

## Scoring (deterministic, `app/scoring.py`)

- Formula: `readiness = Σ freq × match / Σ freq` over **must + nice** skills (rare skills don't count).
- Match values: intermediate, strong or chat-confirmed = 1; basic = 0.5; missing or denied in chat = 0.
- Gaps: must + nice skills with a match below 1, ranked must first, then by frequency.

## Paymob (test mode)

Paymob setup:

1. In the Paymob dashboard (test mode), get the secret key, public key, card integration ID and HMAC secret, and put them in `.env`.
2. For the server-to-server callback, expose the backend with `ngrok http 8000` and set `PUBLIC_BACKEND_URL` to the ngrok URL.

Payment flow:

1. The frontend calls `POST /api/payments/{id}/checkout` and gets back `checkout_url` (Unified Checkout). It opens that URL.
2. Paymob calls `POST /api/payments/paymob/callback?hmac=...`. The backend verifies HMAC-SHA512 and marks the analysis paid only when `success=true` and `pending=false`.
3. Paymob redirects the browser to `GET /api/payments/paymob/callback?...`, which runs the same HMAC check. The backend then redirects to `FRONTEND_URL/?analysis_id=...&payment=paid|failed|pending`. The redirect alone is enough to unlock premium on localhost when ngrok isn't running.
4. The frontend polls `GET /api/payments/{id}/status`, then re-fetches `/plan`.

## API notes for the frontend

- `POST /api/analyze` returns right away. Open the SSE stream, wait for `{step: "done"}`, then call `/results`. If the stream sends `{step: "error"}`, show a retry.
- `/results` before the analysis is done returns `409 NOT_READY`.
- `/chat` with `{message: ""}` returns the current question. Each answer returns an acknowledgement plus the next question.
- `/plan` when not premium has the same shape, but:
  - `weeks` holds only week 1
  - `project` has only `title` (other fields empty)
  - `resources` and `career_path` are `[]`
  - `projected_readiness` is still included
- Checkout also returns `client_secret` and `public_key`, in case you embed Unified Checkout instead of redirecting.
- Errors always look like `{ "error": { "code", "message" } }`.

## Layout

```
app/main.py      routes, error handling, demo routing, payment callbacks
app/graph.py     LangGraph: extract -> market -> score -> discuss <-> score (interrupt per question)
app/extract.py   course map + grounded LLM extraction + keyword fallback
app/scoring.py   readiness + gaps (pure)
app/plan.py      roadmap, resources, project, projection, career path
app/payments.py  Paymob intention + HMAC
app/data.py      CSV loading, alias normalization, market demand
app/llm.py       Claude structured output with timeout
app/mock.py      demo persona result
```
