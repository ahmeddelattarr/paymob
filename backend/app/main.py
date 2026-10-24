import asyncio
import hashlib
import json
import logging
import uuid

from fastapi import BackgroundTasks, FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse, StreamingResponse
from starlette.exceptions import HTTPException

from . import config, graph, llm, mock, payments, plan, scoring
from .data import MARKET, MARKET_SOURCE, POSTINGS, RESOURCES, ROLE_TITLES, SKILLS
from .models import (AnalyzeResponse, ChatRequest, ChatResponse, CheckoutResponse, CompareResponse, PaymentStatus,
                     PlanResponse, ResultsResponse, RolesResponse, Summary)
from .pdf import extract_text

log = logging.getLogger("uvicorn.error")
app = FastAPI(title="Career Readiness API")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

SESSIONS = graph.SESSIONS
SESSIONS[mock.DEMO_ID] = {"role": "backend", "status": "ready", "progress": [], "payment_status": "pending"}


class AppError(HTTPException):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(status, message)
        self.code = code


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException):
    code = getattr(exc, "code", "HTTP_%d" % exc.status_code)
    return JSONResponse({"error": {"code": code, "message": str(exc.detail)}}, exc.status_code)


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError):
    fields = ", ".join(".".join(str(p) for p in e["loc"][1:]) for e in exc.errors())
    return JSONResponse({"error": {"code": "VALIDATION_ERROR", "message": f"Missing or invalid: {fields}"}}, 422)


@app.exception_handler(Exception)
async def unexpected_error(_: Request, exc: Exception):
    log.exception("unhandled error")
    return JSONResponse({"error": {"code": "INTERNAL", "message": "Something went wrong. Please try again."}}, 500)


def _session(aid: str) -> dict:
    s = SESSIONS.get(aid)
    if not s:
        raise AppError(404, "NOT_FOUND", "Analysis not found. Please upload your files again.")
    return s


def _ready(aid: str) -> dict:
    s = _session(aid)
    if s["status"] == "running":
        raise AppError(409, "NOT_READY", "Analysis is still running.")
    if s["status"] == "error":
        raise AppError(500, "ANALYSIS_FAILED", "Analysis failed. Please try again.")
    return s


def _is_premium(s: dict) -> bool:
    return s.get("payment_status") == "paid"


@app.get("/health")
def health(llm_check: bool = False):
    out = {"status": "ok", "llm_key_loaded": llm.available(),
           "data_loaded": {"skills": len(SKILLS), "postings": len(POSTINGS), "resources": len(RESOURCES),
                           "market_source": MARKET_SOURCE},
           "paymob_configured": payments.configured()}
    if llm_check:
        try:
            out["llm_ok"] = bool(llm.structured("Reply with the summary 'ok'.", Summary, fast=True).summary)
        except llm.LLMError as e:
            out["llm_ok"], out["llm_error"] = False, str(e)
    return out


@app.post("/api/analyze", response_model=AnalyzeResponse)
def analyze(background: BackgroundTasks, cv: UploadFile = File(...), curriculum: UploadFile = File(...),
            role: str = Form(...)):
    if role not in ROLE_TITLES:
        raise AppError(400, "INVALID_ROLE", f"Unknown role. Use one of: {', '.join(ROLE_TITLES)}")
    cv_bytes, cur_bytes = cv.file.read(), curriculum.file.read()
    texts = {}
    for label, data in (("CV", cv_bytes), ("curriculum", cur_bytes)):
        try:
            texts[label] = extract_text(data)
        except ValueError:
            raise AppError(422, "NO_TEXT", f"We couldn't read text from your {label} PDF. "
                                           "It may be a scanned image; please upload a text-based PDF.")
    aid = uuid.uuid4().hex
    SESSIONS[aid] = {"role": role, "status": "running", "progress": [], "payment_status": "pending",
                     "file_hash": hashlib.sha256(cv_bytes + b"|" + cur_bytes).hexdigest()}
    background.add_task(graph.run_analysis, aid, texts["CV"], texts["curriculum"])
    return {"analysis_id": aid}


@app.get("/api/analyze/{analysis_id}/stream")
async def stream(analysis_id: str):
    s = _session(analysis_id)

    async def events():
        if analysis_id == mock.DEMO_ID:
            for step, message in mock.STREAM_STEPS:
                yield f"data: {json.dumps({'step': step, 'message': message})}\n\n"
                await asyncio.sleep(0.5)
            yield f"data: {json.dumps({'step': 'done', 'message': 'Results ready'})}\n\n"
            return
        i = 0
        while True:
            while i < len(s["progress"]):
                yield f"data: {json.dumps(s['progress'][i])}\n\n"
                i += 1
                await asyncio.sleep(0.4)  # let the analyzing screen show each step
            if s["status"] != "running" and i >= len(s["progress"]):
                return
            await asyncio.sleep(0.3)

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


def _skills_out(profile: dict) -> list[dict]:
    return [{"skill_id": sid, "skill_name": SKILLS.get(sid, {}).get("name", sid), "level": e["level"],
             "evidence": e["evidence"]}
            for sid, e in sorted(profile.items(), key=lambda kv: -scoring.match(kv[1]))]


@app.get("/api/analyze/{analysis_id}/results", response_model=ResultsResponse)
def results(analysis_id: str):
    if analysis_id == mock.DEMO_ID:
        return mock.RESULTS
    s = _ready(analysis_id)
    st = graph.state_of(analysis_id)
    return {"analysis_id": analysis_id, "role": s["role"], "role_title": ROLE_TITLES[s["role"]],
            "readiness": st["readiness"], "summary": s["summary"],
            "postings_analyzed": MARKET[s["role"]]["sample_size"], "gaps": st["gaps"],
            "skills": _skills_out(st["profile"])}


DEMO_CHAT: dict[str, int] = {}


@app.post("/api/analyze/{analysis_id}/chat", response_model=ChatResponse)
def chat(analysis_id: str, body: ChatRequest):
    if analysis_id == mock.DEMO_ID:
        turn = 0 if not body.message else min(DEMO_CHAT.get(analysis_id, 0) + 1, len(mock.CHAT_SCRIPT) - 1)
        DEMO_CHAT[analysis_id] = turn
        return {"reply": mock.CHAT_SCRIPT[turn], "score_changed": turn == 1, "previous_readiness": 62,
                "readiness": 70 if turn else 62, "gaps": mock.GAPS_AFTER_GIT if turn else mock.RESULTS["gaps"]}
    _ready(analysis_id)
    return graph.chat(analysis_id, body.message)


@app.get("/api/analyze/{analysis_id}/plan", response_model=PlanResponse)
def get_plan(analysis_id: str):
    s = _ready(analysis_id)
    full = mock.PLAN if analysis_id == mock.DEMO_ID else plan.build(s, graph.state_of(analysis_id))
    return full if _is_premium(s) else plan.preview(full)


@app.get("/api/roles", response_model=RolesResponse)
def roles():
    return {"roles": [{"role": r, "role_title": t, "postings_count": MARKET[r]["sample_size"]}
                      for r, t in ROLE_TITLES.items()]}


@app.get("/api/roles/compare/{analysis_id}", response_model=CompareResponse)
def compare(analysis_id: str):
    if analysis_id == mock.DEMO_ID:
        return mock.COMPARE
    _ready(analysis_id)
    profile = graph.state_of(analysis_id)["profile"]
    scores = [{"role": r, "role_title": t, "readiness": scoring.readiness(profile, MARKET[r])}
              for r, t in ROLE_TITLES.items()]
    return {"roles": sorted(scores, key=lambda x: -x["readiness"])}


# --- Payments ---

@app.post("/api/payments/{analysis_id}/checkout", response_model=CheckoutResponse)
def checkout(analysis_id: str):
    _ready(analysis_id)
    try:
        return payments.create_intention(analysis_id)
    except payments.PaymentError as e:
        log.error("paymob checkout failed: %s", e)
        raise AppError(502, "PAYMENT_UNAVAILABLE", "Payment is unavailable right now. Please try again.")


def _apply_payment(analysis_id: str | None, status: str) -> None:
    s = SESSIONS.get(analysis_id or "")
    if s and s.get("payment_status") != "paid":  # never downgrade a verified payment
        s["payment_status"] = status


@app.post("/api/payments/paymob/callback")
async def paymob_callback(request: Request):
    """Server-to-server transaction callback. Marks premium only on a verified, successful payment."""
    body = await request.json()
    obj = body.get("obj") or {}
    if not payments.verify_transaction(obj, request.query_params.get("hmac", "")):
        raise AppError(401, "INVALID_HMAC", "HMAC verification failed")
    aid = payments.analysis_id_from_reference((obj.get("order") or {}).get("merchant_order_id"))
    _apply_payment(aid, payments.outcome(obj.get("success"), obj.get("pending")))
    return {"received": True}


@app.get("/api/payments/paymob/callback")
def paymob_redirect(request: Request):
    """Browser redirect after checkout. Same HMAC check, then send the user back to the frontend."""
    params = dict(request.query_params)
    aid = payments.analysis_id_from_reference(params.get("merchant_order_id"))
    status = "failed"
    if payments.verify_redirect(params):
        status = payments.outcome(params.get("success"), params.get("pending"))
        _apply_payment(aid, status)
    return RedirectResponse(f"{config.FRONTEND_URL}/?analysis_id={aid or ''}&payment={status}")


@app.get("/api/payments/{analysis_id}/status", response_model=PaymentStatus)
def payment_status(analysis_id: str):
    s = _session(analysis_id)
    return {"status": s["payment_status"], "premium": _is_premium(s)}
