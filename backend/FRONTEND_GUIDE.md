# Frontend integration guide

Base URL: `http://localhost:8000`. Interactive docs: `http://localhost:8000/docs`.
Every error looks like `{ "error": { "code": "...", "message": "..." } }`. The `message` is safe to show to users.

## Quick start: demo mode

Use `analysis_id = "demo"` to build every screen without uploading anything. It returns a precomputed persona instantly for `/stream`, `/results`, `/chat`, `/plan` and `/roles/compare`, and payments work on it too.

---

## Screens and endpoints

```
Upload ──> Analyzing (SSE) ──> Results ──> Chat (score updates live)
                                   │
                                   └──> Plan: FREE preview ──[Unlock]──> Paymob ──> back ──> Plan: FULL
                                   └──> Role comparison
```

### 1. Upload: `POST /api/analyze` (multipart/form-data)

| field | type |
|---|---|
| `cv` | PDF file |
| `curriculum` | PDF file (transcript or curriculum) |
| `role` | one of `backend`, `frontend`, `data_analyst`, `ai_ml`, `qa`, `devops` |

→ `200 { "analysis_id": "a7d1…" }` (returns right away; the analysis keeps running in the background)

Errors:
- `422 NO_TEXT`: a PDF is scanned or has no text. Show the message.
- `400 INVALID_ROLE`: the role isn't in the list above.
- `422 VALIDATION_ERROR`: a field is missing.

Use `GET /api/roles` to build the role picker:
`{ roles: [{ role, role_title, postings_count }] }`

### 2. Analyzing screen: `GET /api/analyze/{id}/stream` (Server-Sent Events)

```ts
const es = new EventSource(`${API}/api/analyze/${id}/stream`);
es.onmessage = (e) => {
  const { step, message } = JSON.parse(e.data);
  if (step === "done")  { es.close(); router.push(`/results/${id}`); return; }
  if (step === "error") { es.close(); showError(message); return; }
  addStep(message);   // "Reading your CV", "Analyzing 6 Junior Backend Developer postings in Egypt", "Found 4 gaps"…
};
```
Steps arrive in this order: `cv`, `curriculum`, `market`, `compare`, `gaps`, then `done` (or `error`).

### 3. Results: `GET /api/analyze/{id}/results`

```json
{
  "analysis_id": "…", "role": "backend", "role_title": "Junior Backend Developer",
  "readiness": 47, "summary": "You match 47% of…", "postings_analyzed": 6,
  "gaps":   [{ "skill_id": "git", "skill_name": "Git", "tier": "must", "frequency": 1.0,
               "user_level": "none", "reason": "Not found in your CV or courses" }],
  "skills": [{ "skill_id": "python", "skill_name": "Python", "level": "intermediate",
               "evidence": [{ "source": "cv", "text": "Built a REST API in Python using FastAPI…" }] }]
}
```
- `readiness` is 0–100.
- `frequency` is 0–1, the share of postings that ask for the skill. Show it as a percentage.
- `tier` is `must` or `nice`. Gaps come pre-sorted: must first, then by frequency.
- `level` is `none`, `basic`, `intermediate` or `strong`.
- `evidence[].source` is `cv`, `course` or `chat`. Show evidence as quotes so every claim is backed up.
- Calling this before the stream sends `done` returns `409 NOT_READY`.

### 4. Chat: `POST /api/analyze/{id}/chat`, body `{ "message": "..." }`

- **On first open**, send `{ "message": "" }`. That returns the AI's opening question.
- **Then** send the user's answers.

```json
{ "reply": "Great, I've added Git to your profile. Your CV doesn't mention Docker… Have you used it?",
  "score_changed": true, "previous_readiness": 47, "readiness": 60, "gaps": [ … ] }
```
- When `score_changed` is true, animate `previous_readiness → readiness` and replace the gaps list.
- The AI asks up to 4 questions. After that the reply points the user to their plan, and further messages get the same closing reply.

### 5. Role comparison: `GET /api/roles/compare/{id}`

→ `{ roles: [{ role, role_title, readiness }] }`, sorted from best to worst.
This is a premium feature in the spec. The backend doesn't block it, so hide it behind `premium` in the UI.

---

## Free vs premium

The same endpoint serves both: `GET /api/analyze/{id}/plan`. Check the `premium` field.

| field | free (`premium: false`) | premium (`premium: true`) |
|---|---|---|
| `weeks` | week 1 only | all 4 weeks |
| `project.title` | ✓ | ✓ |
| `project.description`, `skills_covered`, `milestones` | `""` / `[]` | ✓ |
| `resources` | `[]` | ✓ (free and Arabic resources first) |
| `career_path` | `[]` | 4 steps |
| `projected_readiness` | ✓ (use it as the upsell: "reach 89%") | ✓ |

The response shape is identical in both cases, so one component works: show locked placeholders when `premium` is false.

```json
{ "premium": true,
  "weeks": [{ "week": 1, "focus_skills": ["docker"], "tasks": ["…"], "hours": 7 }],
  "project": { "title": "…", "description": "…", "skills_covered": ["docker","git"], "milestones": ["…"] },
  "resources": [{ "skill_id": "docker", "title": "…", "url": "…", "type": "video", "language": "ar", "hours": 4, "free": true }],
  "projected_readiness": 89,
  "career_path": [{ "step": 1, "title": "Junior Backend Developer", "description": "…" }] }
```

---

## Payment flow (Paymob, test mode, 99 EGP)

```
[Unlock premium] click
   │ POST /api/payments/{id}/checkout
   ▼
{ checkout_url, amount_egp: 99, client_secret, public_key }
   │ window.location.href = checkout_url        (Paymob Unified Checkout page)
   ▼
user pays on Paymob
   │ Paymob → backend (verifies HMAC, marks paid) → redirects browser to:
   ▼
FRONTEND_URL/?analysis_id={id}&payment=paid|failed|pending
   │ on that page: GET /api/payments/{id}/status  → { status, premium }
   ▼
premium === true → re-fetch /plan → show full plan
```

Frontend responsibilities:
1. **Unlock button** calls `POST /api/payments/{id}/checkout`, then sets `window.location.href = checkout_url`.
   - `502 PAYMENT_UNAVAILABLE` means Paymob is down or misconfigured. Show the message.
   - The analysis must be finished first; otherwise you get `409 NOT_READY`.
2. **Return landing:** Paymob comes back to `http://localhost:3000/?analysis_id=…&payment=…`, which is the root page. Read both query params there and route to the plan page. To use a different path, tell the backend person to change `FRONTEND_URL` or the redirect path.
3. **Never trust `payment=paid` from the URL.** Always confirm with `GET /api/payments/{id}/status`. If it's still `pending`, poll every 2 s for about 20 s, because the server-to-server confirmation can arrive a moment later.
4. **Keep `analysis_id` in `localStorage`** before redirecting, in case the query param is lost.

`GET /api/payments/{id}/status` returns `{ "status": "pending" | "paid" | "failed", "premium": boolean }`

Test card: `5123 4567 8901 2346`, any name, a future expiry, CVV `123`.
Don't call `/api/payments/paymob/callback` from the frontend; only Paymob calls it.

---

## TypeScript types

```ts
type Level = "none" | "basic" | "intermediate" | "strong";
type Evidence = { source: "cv" | "course" | "chat"; text: string };
type Skill = { skill_id: string; skill_name: string; level: Level; evidence: Evidence[] };
type Gap = { skill_id: string; skill_name: string; tier: "must" | "nice"; frequency: number; user_level: Level; reason: string };

type Results = { analysis_id: string; role: string; role_title: string; readiness: number; summary: string;
                 postings_analyzed: number; gaps: Gap[]; skills: Skill[] };
type ChatResponse = { reply: string; score_changed: boolean; previous_readiness: number; readiness: number; gaps: Gap[] };

type Week = { week: number; focus_skills: string[]; tasks: string[]; hours: number };
type Project = { title: string; description: string; skills_covered: string[]; milestones: string[] };
type Resource = { skill_id: string; title: string; url: string; type: "video" | "course" | "article" | "docs";
                  language: "ar" | "en"; hours: number; free: boolean };
type Plan = { premium: boolean; weeks: Week[]; project: Project; resources: Resource[];
              projected_readiness: number; career_path: { step: number; title: string; description: string }[] };

type Checkout = { checkout_url: string; amount_egp: number; client_secret: string; public_key: string };
type PaymentStatus = { status: "pending" | "paid" | "failed"; premium: boolean };
type ApiError = { error: { code: string; message: string } };
```

## Error codes

| code | HTTP | when |
|---|---|---|
| `NO_TEXT` | 422 | A PDF has no readable text (scanned) |
| `INVALID_ROLE` | 400 | Unknown role |
| `VALIDATION_ERROR` | 422 | Missing or invalid field |
| `NOT_FOUND` | 404 | Unknown `analysis_id` (also after a backend restart; ask the user to re-upload) |
| `NOT_READY` | 409 | Analysis still running |
| `ANALYSIS_FAILED` | 500 | The analysis crashed; offer a retry |
| `PAYMENT_UNAVAILABLE` | 502 | Paymob error |
| `INTERNAL` | 500 | Anything else |
