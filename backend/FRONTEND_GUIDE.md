# Frontend Integration Spec: Career Readiness API

This is the complete contract between the Next.js frontend and the FastAPI backend.
It is written so a developer or an AI coding agent can build the whole frontend from this file alone.
Everything here matches the running backend; nothing is aspirational.

---

## 0. Essentials

| | |
|---|---|
| Base URL (local) | `http://localhost:8000` (put it in `NEXT_PUBLIC_API_URL`) |
| Interactive docs | `http://localhost:8000/docs` |
| CORS | Allowed origin: `http://localhost:3000`. On another port or host, ask the backend dev to add it to `CORS_ORIGINS`. |
| Auth | None. The `analysis_id` is the only identifier. |
| Content type | JSON everywhere, except `POST /api/analyze` (multipart) and `/stream` (Server-Sent Events). |
| Demo shortcut | `analysis_id = "demo"` works on every endpoint and returns a precomputed persona instantly (see §7). |

### Error format (every endpoint, every failure)

```json
{ "error": { "code": "NOT_READY", "message": "Analysis is still running." } }
```

- Branch your logic on `error.code`.
- `error.message` is user-friendly, so you can show it as-is.
- Always read the HTTP status **and** the body. Don't assume a 200.

### Measured latencies (real Gemini, demo persona)

| Operation | Typical time | UI |
|---|---|---|
| `POST /api/analyze` | under 1 s (PDF parsing only) | button spinner |
| Analysis, upload to `done` event | **~15–25 s** | analyzing screen with streamed steps |
| `POST /chat` with an answer | **1–3 s** | typing indicator |
| First `GET /plan` per analysis | **up to ~10 s** (AI writes the project, then it's cached) | skeleton loader |
| Later `GET /plan` calls | under 100 ms | none |
| `POST /payments/{id}/checkout` | 1–3 s (calls Paymob) | button spinner |
| Everything else | under 100 ms | none |

Same files uploaded again: the backend caches the extracted profile by file hash, so the second analysis takes about 3 s and gives an identical score.

---

## 1. Screens and user flow

```
┌────────┐  POST /api/analyze   ┌────────────┐  SSE "done"  ┌─────────┐
│ Upload │ ───────────────────► │ Analyzing  │ ───────────► │ Results │
└────────┘   {analysis_id}      │ (SSE steps)│              └────┬────┘
     ▲                          └─────┬──────┘                   │
     │ 404 NOT_FOUND / SSE "error"    │                          ├──► Chat (live score)
     └────────────────────────────────┘                          │
                                                                 ├──► Plan
                                                                 │     ├─ premium=false → preview + [Unlock 99 EGP]
                                                                 │     └─ premium=true  → full plan
                                                                 │
                                                                 └──► Role comparison (premium only in UI)

[Unlock] → POST /payments/{id}/checkout → redirect to Paymob → user pays
        → Paymob → backend verifies → browser lands on FRONTEND_URL/?analysis_id=…&payment=…
        → GET /payments/{id}/status → if premium → GET /plan (full)
```

### State to keep on the client

| Key | Where | Why |
|---|---|---|
| `analysis_id` | URL path (`/results/[id]`) **and** `localStorage.lastAnalysisId` | It has to survive the Paymob redirect |
| `role` | `localStorage` (optional) | For display only |
| Chat messages | React state only | The backend keeps the chat state; it doesn't return history |

---

## 2. Endpoints

### 2.1 `GET /api/roles`: role picker

**200**
```json
{ "roles": [
  { "role": "backend", "role_title": "Junior Backend Developer", "postings_count": 6 },
  { "role": "frontend", "role_title": "Junior Frontend Developer", "postings_count": 2 },
  { "role": "data_analyst", "role_title": "Junior Data Analyst", "postings_count": 3 },
  { "role": "ai_ml", "role_title": "Junior AI/ML Engineer", "postings_count": 3 },
  { "role": "qa", "role_title": "Junior QA Engineer", "postings_count": 2 },
  { "role": "devops", "role_title": "Junior DevOps Engineer", "postings_count": 2 }
]}
```
Errors: none. The `postings_count` values will change when the real dataset lands, so don't hardcode them.

---

### 2.2 `POST /api/analyze`: start an analysis

**Request:** `multipart/form-data`

| field | type | rules |
|---|---|---|
| `cv` | file | PDF with selectable text |
| `curriculum` | file | PDF (transcript or curriculum) with selectable text |
| `role` | string | exactly one of `backend`, `frontend`, `data_analyst`, `ai_ml`, `qa`, `devops` |

```ts
const fd = new FormData();
fd.append("cv", cvFile);
fd.append("curriculum", curriculumFile);
fd.append("role", role);
const res = await fetch(`${API}/api/analyze`, { method: "POST", body: fd }); // do NOT set Content-Type manually
```

**200:** `{ "analysis_id": "c97972c3e5a8409d81cb7613241718c1" }`
The response returns right away; the analysis runs in the background. Next, open the stream (§2.3).

| Status | `code` | `message` (exact) | UI action |
|---|---|---|---|
| 400 | `INVALID_ROLE` | `Unknown role. Use one of: backend, frontend, data_analyst, ai_ml, qa, devops` | Bug on our side; the picker must send a valid role |
| 422 | `NO_TEXT` | `We couldn't read text from your CV PDF. It may be a scanned image; please upload a text-based PDF.` | Show it under the **CV** input |
| 422 | `NO_TEXT` | `We couldn't read text from your curriculum PDF. It may be a scanned image; please upload a text-based PDF.` | Show it under the **curriculum** input (check whether the message contains `CV` or `curriculum`) |
| 422 | `VALIDATION_ERROR` | `Missing or invalid: cv` (lists the missing fields, e.g. `cv, role`) | Highlight the missing inputs |
| 500 | `INTERNAL` | `Something went wrong. Please try again.` | Toast plus retry |

Client-side checks to add before uploading: both files present, `.pdf` extension, size under 10 MB.

---

### 2.3 `GET /api/analyze/{id}/stream`: analyzing screen (SSE)

Each event is a `data:` line with JSON `{ "step": string, "message": string }`.

Order: `cv` → `curriculum` → `market` → `compare` → `gaps` → `done`. If the analysis crashes, the last event is `error` instead of `done`.

| step | example message |
|---|---|
| `cv` | `Reading your CV` |
| `curriculum` | `Reading your curriculum` |
| `market` | `Analyzing 6 Junior Backend Developer postings in Egypt` |
| `compare` | `Comparing your skills` |
| `gaps` | `Found 10 gaps` |
| `done` | `Results ready` → go to Results |
| `error` | `Analysis failed. Please try again.` → show the message plus a "Try again" button back to Upload |

```ts
useEffect(() => {
  const es = new EventSource(`${API}/api/analyze/${id}/stream`);
  es.onmessage = (e) => {
    const { step, message } = JSON.parse(e.data) as { step: string; message: string };
    if (step === "done")  { es.close(); router.replace(`/results/${id}`); return; }
    if (step === "error") { es.close(); setError(message); return; }
    setSteps((s) => (s.some((x) => x.step === step) ? s : [...s, { step, message }]));
  };
  es.onerror = () => { es.close(); setError("Connection lost. Please try again."); };
  return () => es.close();
}, [id]);
```

Notes:
- The stream **replays all steps from the start** each time it's opened, so React Strict Mode double-mounting and page refreshes are safe. Dedupe by `step`, as in the code above.
- Steps arrive about 0.4 s apart. Between `curriculum` and `market` there's a gap of about 10–15 s while the AI reads the CV, so animate the current step (spinner or pulsing dot).
- Unknown `id`: the server replies `404` JSON before the stream starts. `EventSource` can't read that body; it just fires `onerror`. Treat `onerror` before any message as "analysis not found" and send the user to Upload.
- On `demo`, the stream sends 5 scripted steps 0.5 s apart, then `done`.

---

### 2.4 `GET /api/analyze/{id}/results`: results screen

**200**
```json
{
  "analysis_id": "c97972c3…",
  "role": "backend",
  "role_title": "Junior Backend Developer",
  "readiness": 47,
  "summary": "With a solid foundation in Python, Data Structures & Algorithms, and SQL, you're well-prepared…",
  "postings_analyzed": 6,
  "gaps": [
    { "skill_id": "git", "skill_name": "Git", "tier": "must", "frequency": 1.0, "user_level": "none",
      "reason": "Not found in your CV or courses" },
    { "skill_id": "testing", "skill_name": "Unit Testing", "tier": "must", "frequency": 0.5, "user_level": "basic",
      "reason": "Only seen in a course, no project" }
  ],
  "skills": [
    { "skill_id": "python", "skill_name": "Python", "level": "strong",
      "evidence": [
        { "source": "cv", "text": "Fixed bugs in an internal Python reporting tool." },
        { "source": "course", "text": "CS101 Introduction to Programming (Python)" }
      ] }
  ]
}
```

| Field | Meaning / how to render |
|---|---|
| `readiness` | Integer 0–100. Big gauge. |
| `summary` | 2 sentences written by the AI. Show it under the gauge. |
| `postings_analyzed` | "Based on N junior job postings in Egypt" |
| `gaps[]` | Already sorted (must first, then by frequency). Don't re-sort. |
| `gaps[].tier` | `must` → red "Must-have" badge; `nice` → amber "Nice to have" |
| `gaps[].frequency` | 0–1. Show `Math.round(f * 100)` + "% of postings". |
| `gaps[].user_level` | `none`, `basic`, `intermediate` or `strong` |
| `gaps[].reason` | One of: `Not found in your CV or courses` · `Only seen in a course, no project` · `Only basic experience found` · `You said you haven't used it yet` |
| `skills[]` | Sorted strongest first. `level` is `none`, `basic`, `intermediate` or `strong`. |
| `skills[].evidence[]` | **Show it.** This is the trust feature: every skill is backed by a quote. `source` is `cv` (📄 "From your CV"), `course` (🎓 "From your courses") or `chat` (💬 "You told us"). |

After the chat changes something, `/results` returns the **updated** readiness, gaps and skills (including `chat` evidence). `summary` is **not** regenerated.

| Status | `code` | `message` | UI action |
|---|---|---|---|
| 404 | `NOT_FOUND` | `Analysis not found. Please upload your files again.` | Show the message and a link to Upload (also happens after a backend restart) |
| 409 | `NOT_READY` | `Analysis is still running.` | Go to the Analyzing screen (or retry after 2 s) |
| 500 | `ANALYSIS_FAILED` | `Analysis failed. Please try again.` | Show it with a link to Upload |

---

### 2.5 `POST /api/analyze/{id}/chat`: discussion chat

**Request:** `{ "message": string }` (JSON, `Content-Type: application/json`)

**Protocol:**
1. When the chat opens, send `{ "message": "" }`. That returns the AI's first question and doesn't change anything. It's safe to call twice, and the question is the same.
2. Send each user answer as `{ "message": "<text>" }`. Arabic, English and Franco-Arabic all work.
3. Each answered turn's `reply` = an acknowledgement + the next question, in one string.
4. After at most **4 questions**, the reply ends with: `That's everything I wanted to check. Open your plan to see how to close the remaining gaps.` Any further message returns that same closing line with `score_changed: false`. Then show a "See my plan" button.

**200**
```json
{
  "reply": "That's great to hear you're using Git for your projects! Your CV doesn't mention Docker, and 83% of Junior Backend Developer postings ask for it. Have you used it?",
  "score_changed": true,
  "previous_readiness": 47,
  "readiness": 60,
  "gaps": [ /* same shape as results.gaps, updated */ ]
}
```

| Field | Use |
|---|---|
| `reply` | Append it as an AI bubble |
| `score_changed` | If true, animate the score from `previous_readiness` to `readiness` (count-up) and replace the gaps list with `gaps` |
| `gaps` | Always the current full list. Use it to refresh a sidebar. |

How answers affect the score (so the UI copy makes sense):

| User says | Effect |
|---|---|
| "Yes, I used it in a project / at work" | Skill confirmed. Full credit; the gap disappears. Score goes up. |
| "Only watched a tutorial" | Counted as `basic` (half credit). Score may go up a little. |
| "No" | Gap stays with reason `You said you haven't used it yet`. Score **never goes down**. |

| Status | `code` | `message` | UI action |
|---|---|---|---|
| 404 | `NOT_FOUND` | `Analysis not found. Please upload your files again.` | Link to Upload |
| 409 | `NOT_READY` | `Analysis is still running.` | Don't open the chat before results are ready |
| 422 | `VALIDATION_ERROR` | `Missing or invalid: message` | Only happens if the body isn't JSON; always send `{ message }` |
| 500 | `INTERNAL` | `Something went wrong. Please try again.` | Keep the user's text in the input and offer a retry |

If the AI provider is down, the chat still answers using simple yes/no detection, and the response shape is identical.

---

### 2.6 `GET /api/analyze/{id}/plan`: plan (free preview or full)

There's one endpoint for both tiers. **Always check `premium`.** The shape is identical in both cases; locked fields are empty.

**200, premium = false (preview)**
```json
{
  "premium": false,
  "weeks": [ { "week": 1, "focus_skills": ["git", "nodejs"], "tasks": ["Study Git: …", "Practice Git …"], "hours": 15 } ],
  "project": { "title": "Containerized To-Do List API with CI/CD", "description": "", "skills_covered": [], "milestones": [] },
  "resources": [],
  "projected_readiness": 86,
  "career_path": []
}
```

**200, premium = true (full)**
```json
{
  "premium": true,
  "weeks": [
    { "week": 1, "focus_skills": ["docker", "javascript"], "tasks": ["Study Docker: Docker tutorials in Arabic (YouTube search) (~4h)", "Practice Docker in a small exercise and push it to GitHub"], "hours": 20 },
    { "week": 2, "focus_skills": ["testing", "linux"], "tasks": ["…"], "hours": 14 },
    { "week": 3, "focus_skills": ["ci_cd"], "tasks": ["…"], "hours": 5 },
    { "week": 4, "focus_skills": ["docker", "testing", "ci_cd"], "tasks": ["Build: Containerized To-Do List API with CI/CD", "…milestones"], "hours": 10 }
  ],
  "project": { "title": "…", "description": "…", "skills_covered": ["docker", "testing", "ci_cd"], "milestones": ["…", "…"] },
  "resources": [
    { "skill_id": "docker", "title": "Docker tutorials in Arabic (YouTube search)", "url": "https://…", "type": "video", "language": "ar", "hours": 4, "free": true }
  ],
  "projected_readiness": 86,
  "career_path": [
    { "step": 1, "title": "Junior Backend Developer", "description": "0-2 years: ship features under guidance and learn the team's stack." },
    { "step": 2, "title": "Backend Developer", "description": "2-4 years: own features end to end and make design decisions." },
    { "step": 3, "title": "Senior Backend Engineer", "description": "4-7 years: lead system design and mentor juniors." },
    { "step": 4, "title": "Tech Lead / Architect", "description": "7+ years: set technical direction across teams." }
  ]
}
```

What to render in each tier:

| Section | Free | Premium |
|---|---|---|
| Week 1 | ✅ show | ✅ |
| Weeks 2–4 | 🔒 3 blurred placeholder cards | ✅ |
| Project title | ✅ | ✅ |
| Project description, skills, milestones | 🔒 | ✅ |
| Resources (links) | 🔒 | ✅. Badge `ar` → "عربي", `free` → "Free", show `hours`. |
| Career path | 🔒 | ✅ timeline |
| `projected_readiness` | ✅ **upsell**: "Finish this plan to reach 86% (you're at 47%)" + **Unlock for 99 EGP** | ✅ |
| Role comparison (§2.7) | 🔒 | ✅ |

- `focus_skills` and `skills_covered` contain **skill ids** (e.g. `ci_cd`). Map them to names with the `skills`/`gaps` arrays from `/results` (`skill_id` → `skill_name`), or show them as-is in Title Case.
- `weeks` can have fewer than 4 entries if the user has few gaps. Render whatever comes back.
- Errors: same as `/results` (404 `NOT_FOUND`, 409 `NOT_READY`, 500 `ANALYSIS_FAILED`).

---

### 2.7 `GET /api/roles/compare/{id}`: readiness for all 6 roles

**200:** sorted from highest to lowest
```json
{ "roles": [
  { "role": "qa", "role_title": "Junior QA Engineer", "readiness": 67 },
  { "role": "backend", "role_title": "Junior Backend Developer", "readiness": 64 }
]}
```
- Render it as a horizontal bar chart and highlight the role the user picked.
- **Premium feature: hide it or blur it when `premium` is false.** The backend doesn't enforce this.
- Errors: same as `/results`.

---

### 2.8 Payments (Paymob, test mode, 99 EGP)

#### `POST /api/payments/{id}/checkout`

No body.

**200**
```json
{
  "checkout_url": "https://accept.paymob.com/unifiedcheckout/?publicKey=egy_pk_test_…&clientSecret=egy_csk_test_…",
  "amount_egp": 99,
  "client_secret": "egy_csk_test_…",
  "public_key": "egy_pk_test_…"
}
```
Redirect with `window.location.href = checkout_url`. Don't open it in a popup or iframe. `client_secret` and `public_key` are only needed if you embed Paymob's Unified Checkout instead of redirecting.

| Status | `code` | `message` | UI action |
|---|---|---|---|
| 404 | `NOT_FOUND` | `Analysis not found. Please upload your files again.` | Link to Upload |
| 409 | `NOT_READY` | `Analysis is still running.` | Disable the Unlock button until results are ready |
| 500 | `ANALYSIS_FAILED` | `Analysis failed. Please try again.` | Link to Upload |
| 502 | `PAYMENT_UNAVAILABLE` | `Payment is unavailable right now. Please try again.` | Toast; keep the button enabled for a retry |

#### `GET /api/payments/{id}/status`

**200:** `{ "status": "pending" | "paid" | "failed", "premium": boolean }`
- `premium === (status === "paid")`.
- Works at any time, even while the analysis is running.
- Error: 404 `NOT_FOUND`.

#### `POST /api/payments/paymob/callback` and `GET /api/payments/paymob/callback`

**Paymob calls these, never the frontend.** The backend verifies Paymob's HMAC signature, and only a verified successful payment unlocks premium. A paid status can never be downgraded.

#### Full payment sequence

```
1. User clicks "Unlock for 99 EGP"
2. localStorage.setItem("lastAnalysisId", id)
3. POST /api/payments/{id}/checkout   →  { checkout_url }
4. window.location.href = checkout_url        (Paymob page; user enters the card)
5. Paymob → backend (HMAC verified, analysis marked paid)
6. Backend redirects the browser to:
      http://localhost:3000/?analysis_id={id}&payment=paid      (or failed / pending)
7. Root page "/" reads the query params:
      id = searchParams.analysis_id || localStorage.lastAnalysisId
      → navigate to /plan/{id}?payment=…  (or wherever the plan page lives)
8. Plan page: GET /api/payments/{id}/status
      premium === true   → toast "Premium unlocked 🎉" → GET /plan (full)
      status === "pending" → poll /status every 2 s, up to 10 times, then show
                             "Payment is processing, refresh in a minute"
      status === "failed"  → toast "Payment failed. You were not charged." → keep the preview
```

Rules:
- **The landing URL is the root page `/`.** Handle `analysis_id` and `payment` query params there. To land somewhere else, the backend changes `FRONTEND_URL` or the redirect path (a one-line change; ask).
- **Never unlock based on `?payment=paid` alone.** Always confirm with `/status`. The query param only decides which message to show.
- After a successful payment, re-fetch `/plan` **and** show role comparison.

Test card (sandbox): `5123 4567 8901 2346`, any name, a future expiry, CVV `123`, then accept the test 3-D Secure page. A real sandbox payment has already been tested end to end.

---

### 2.9 `GET /health`: optional

`{ "status": "ok", "llm_key_loaded": true, "data_loaded": {…}, "paymob_configured": true }`
Use it to show a "backend offline" banner if the request fails.

---

## 3. All error codes

| HTTP | `code` | Exact `message` | Endpoints | What the UI does |
|---|---|---|---|---|
| 400 | `INVALID_ROLE` | `Unknown role. Use one of: backend, frontend, data_analyst, ai_ml, qa, devops` | analyze | Fix the role picker |
| 404 | `NOT_FOUND` | `Analysis not found. Please upload your files again.` | all `/{id}` endpoints | Message + "Upload again" button → `/`. Also happens after a backend restart. |
| 409 | `NOT_READY` | `Analysis is still running.` | results, chat, plan, compare, checkout | Go to the Analyzing screen |
| 422 | `NO_TEXT` | `We couldn't read text from your CV PDF. It may be a scanned image; please upload a text-based PDF.` (or `curriculum PDF`) | analyze | Inline error under the file input |
| 422 | `VALIDATION_ERROR` | `Missing or invalid: <fields>` | analyze, chat | Highlight the fields |
| 500 | `ANALYSIS_FAILED` | `Analysis failed. Please try again.` | results, chat, plan, compare, checkout | Message + "Upload again" |
| 500 | `INTERNAL` | `Something went wrong. Please try again.` | any | Toast + retry |
| 502 | `PAYMENT_UNAVAILABLE` | `Payment is unavailable right now. Please try again.` | checkout | Toast + retry |
| 404 | `HTTP_404` | `Not Found` | wrong URL | Bug: check the path |
| 405 | `HTTP_405` | `Method Not Allowed` | wrong method | Bug: check GET vs POST |
| — | network error | `fetch` throws | any | "Can't reach the server. Is the backend running?" |

SSE stream failure: an event `{ "step": "error", "message": "Analysis failed. Please try again." }`.

---

## 4. TypeScript types (copy as-is)

```ts
export type Role = "backend" | "frontend" | "data_analyst" | "ai_ml" | "qa" | "devops";
export type Level = "none" | "basic" | "intermediate" | "strong";
export type Tier = "must" | "nice";

export type Evidence = { source: "cv" | "course" | "chat"; text: string };
export type Skill = { skill_id: string; skill_name: string; level: Level; evidence: Evidence[] };
export type Gap = {
  skill_id: string; skill_name: string; tier: Tier; frequency: number; user_level: Level;
  reason: "Not found in your CV or courses" | "Only seen in a course, no project"
        | "Only basic experience found" | "You said you haven't used it yet";
};

export type RoleInfo = { role: Role; role_title: string; postings_count: number };
export type AnalyzeResponse = { analysis_id: string };
export type StreamEvent = { step: "cv" | "curriculum" | "market" | "compare" | "gaps" | "done" | "error"; message: string };

export type Results = {
  analysis_id: string; role: Role; role_title: string; readiness: number; summary: string;
  postings_analyzed: number; gaps: Gap[]; skills: Skill[];
};
export type ChatResponse = { reply: string; score_changed: boolean; previous_readiness: number; readiness: number; gaps: Gap[] };

export type Week = { week: number; focus_skills: string[]; tasks: string[]; hours: number };
export type Project = { title: string; description: string; skills_covered: string[]; milestones: string[] };
export type Resource = {
  skill_id: string; title: string; url: string; type: "video" | "course" | "article" | "docs";
  language: "ar" | "en"; hours: number; free: boolean;
};
export type CareerStep = { step: number; title: string; description: string };
export type Plan = {
  premium: boolean; weeks: Week[]; project: Project; resources: Resource[];
  projected_readiness: number; career_path: CareerStep[];
};
export type Compare = { roles: { role: Role; role_title: string; readiness: number }[] };

export type Checkout = { checkout_url: string; amount_egp: number; client_secret: string; public_key: string };
export type PaymentStatus = { status: "pending" | "paid" | "failed"; premium: boolean };

export type ApiErrorCode =
  | "INVALID_ROLE" | "NOT_FOUND" | "NOT_READY" | "NO_TEXT" | "VALIDATION_ERROR"
  | "ANALYSIS_FAILED" | "INTERNAL" | "PAYMENT_UNAVAILABLE" | `HTTP_${number}`;
export type ApiErrorBody = { error: { code: ApiErrorCode; message: string } };
```

## 5. API client (copy as-is)

```ts
// lib/api.ts
const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API}${path}`, init);
  } catch {
    throw new ApiError(0, "NETWORK", "Can't reach the server. Please check your connection and try again.");
  }
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    throw new ApiError(res.status, body?.error?.code ?? `HTTP_${res.status}`,
                       body?.error?.message ?? "Something went wrong. Please try again.");
  }
  return body as T;
}

const json = (data: unknown): RequestInit => ({
  method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data),
});

export const api = {
  roles:   () => req<{ roles: RoleInfo[] }>("/api/roles"),
  analyze: (cv: File, curriculum: File, role: Role) => {
    const fd = new FormData();
    fd.append("cv", cv); fd.append("curriculum", curriculum); fd.append("role", role);
    return req<AnalyzeResponse>("/api/analyze", { method: "POST", body: fd });
  },
  streamUrl: (id: string) => `${API}/api/analyze/${id}/stream`,
  results: (id: string) => req<Results>(`/api/analyze/${id}/results`),
  chat:    (id: string, message = "") => req<ChatResponse>(`/api/analyze/${id}/chat`, json({ message })),
  plan:    (id: string) => req<Plan>(`/api/analyze/${id}/plan`),
  compare: (id: string) => req<Compare>(`/api/roles/compare/${id}`),
  checkout: (id: string) => req<Checkout>(`/api/payments/${id}/checkout`, { method: "POST" }),
  paymentStatus: (id: string) => req<PaymentStatus>(`/api/payments/${id}/status`),
};
```

Usage pattern for errors:
```ts
try { setResults(await api.results(id)); }
catch (e) {
  if (e instanceof ApiError && e.code === "NOT_READY") router.replace(`/analyzing/${id}`);
  else if (e instanceof ApiError && (e.code === "NOT_FOUND" || e.code === "ANALYSIS_FAILED")) setFatal(e.message);
  else toast.error((e as Error).message);
}
```

---

## 6. Suggested routes (Next.js App Router)

| Route | Calls | Notes |
|---|---|---|
| `/` | `GET /api/roles`, `POST /api/analyze` | Upload form. **Also handles the Paymob return** (`?analysis_id&payment`) → redirect to `/plan/[id]?payment=…` |
| `/analyzing/[id]` | `GET …/stream` | Steps list; on `done` → `/results/[id]` |
| `/results/[id]` | `GET …/results` | Gauge, summary, gaps, skills with evidence, buttons to Chat and Plan |
| `/chat/[id]` (or a panel on results) | `POST …/chat` | Opening call with `""`; animate the score on `score_changed` |
| `/plan/[id]` | `GET …/payments/{id}/status`, `GET …/plan`, `GET /api/roles/compare/{id}` (premium), `POST …/checkout` | Preview vs full; unlock button; payment toasts |

---

## 7. Demo mode (`analysis_id = "demo"`)

Use it for UI development and as a fallback during the live demo.

| Endpoint | Behavior on `demo` |
|---|---|
| `/stream` | 5 scripted steps, then `done` |
| `/results` | Readiness 62, 4 gaps (Docker, Git, Unit Testing, Redis), 4 skills with evidence |
| `/chat` | Scripted: `""` → Git question; any answer → score 62 → 70 + Docker question; next answer → closing line |
| `/plan` | Full mock plan. Preview or full depending on the payment status of `demo`. |
| `/roles/compare` | 6 mock roles |
| `/payments/demo/checkout` | **Real Paymob sandbox checkout**, and payment really unlocks `demo` |

The demo's payment status lives in backend memory and resets when the backend restarts.

---

## 8. Gotchas

1. **Backend restart = every analysis is gone** (in-memory). Any `/{id}` call then returns `404 NOT_FOUND`; send the user back to Upload.
2. **Don't set `Content-Type` on the upload request.** The browser sets the multipart boundary.
3. **SSE replays from the start.** Dedupe steps by `step`.
4. **Don't call `/results`, `/chat`, `/plan` or `/checkout` before the `done` event**, or you get `409 NOT_READY`.
5. **Chat history isn't stored server-side.** Keep the bubbles in React state. On reload, call `chat("")` to get the current pending question.
6. **The first `/plan` call is slow (~10 s)**, so show a skeleton. Later calls are instant.
7. **Premium is enforced on `/plan` by the backend, but role comparison is not.** Gate it in the UI.
8. **Skill ids vs names:** `focus_skills` and `skills_covered` hold ids. Map them with `/results` data.
9. **Percentages:** `frequency` is 0–1. Multiply by 100 for display.
10. **Paymob return lands on `/`**, not the plan page.
