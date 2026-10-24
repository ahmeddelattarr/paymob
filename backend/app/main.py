import asyncio
import json
import uuid

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from starlette.exceptions import HTTPException

from . import config, mock
from .models import (AnalyzeResponse, ChatRequest, ChatResponse, CheckoutResponse, CompareResponse, PaymentStatus,
                     PlanResponse, ResultsResponse, RolesResponse)

app = FastAPI(title="Career Readiness API")
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])


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
    return JSONResponse({"error": {"code": "VALIDATION_ERROR", "message": str(exc.errors())}}, 422)


@app.get("/health")
def health():
    return {"status": "ok", "llm_key_loaded": bool(config.ANTHROPIC_API_KEY), "data_loaded": True, "mock": True}


# ponytail: checkpoint 2 — every endpoint returns mock data in the contract shape.

@app.post("/api/analyze", response_model=AnalyzeResponse)
async def analyze(cv: UploadFile = File(...), curriculum: UploadFile = File(...), role: str = Form(...)):
    return {"analysis_id": uuid.uuid4().hex}


@app.get("/api/analyze/{analysis_id}/stream")
async def stream(analysis_id: str):
    async def events():
        for step, message in mock.STREAM_STEPS:
            yield f"data: {json.dumps({'step': step, 'message': message})}\n\n"
            await asyncio.sleep(0.5)
        yield f"data: {json.dumps({'step': 'done', 'message': 'Results ready'})}\n\n"
    return StreamingResponse(events(), media_type="text/event-stream")


@app.get("/api/analyze/{analysis_id}/results", response_model=ResultsResponse)
def results(analysis_id: str):
    return {**mock.RESULTS, "analysis_id": analysis_id}


MOCK_CHAT_TURNS: dict[str, int] = {}


@app.post("/api/analyze/{analysis_id}/chat", response_model=ChatResponse)
def chat(analysis_id: str, body: ChatRequest):
    turn = 0 if not body.message else min(MOCK_CHAT_TURNS.get(analysis_id, 0) + 1, len(mock.CHAT_SCRIPT) - 1)
    MOCK_CHAT_TURNS[analysis_id] = turn
    changed = turn == 1
    return {"reply": mock.CHAT_SCRIPT[turn], "score_changed": changed, "previous_readiness": 62,
            "readiness": 70 if turn else 62, "gaps": mock.GAPS_AFTER_GIT if turn else mock.RESULTS["gaps"]}


MOCK_PAID: set[str] = set()


@app.get("/api/analyze/{analysis_id}/plan", response_model=PlanResponse)
def plan(analysis_id: str):
    return {**mock.PLAN, "premium": analysis_id in MOCK_PAID}


@app.get("/api/roles", response_model=RolesResponse)
def roles():
    return {"roles": [{"role": r["role"], "role_title": r["role_title"], "postings_count": 18}
                      for r in mock.COMPARE["roles"]]}


@app.get("/api/roles/compare/{analysis_id}", response_model=CompareResponse)
def compare(analysis_id: str):
    return mock.COMPARE


@app.post("/api/payments/{analysis_id}/checkout", response_model=CheckoutResponse)
def checkout(analysis_id: str):
    MOCK_PAID.add(analysis_id)
    return {"checkout_url": f"{config.FRONTEND_URL}/plan?mock_paid=1", "amount_egp": config.PREMIUM_PRICE_EGP,
            "client_secret": "mock", "public_key": "mock"}


@app.get("/api/payments/{analysis_id}/status", response_model=PaymentStatus)
def payment_status(analysis_id: str):
    paid = analysis_id in MOCK_PAID
    return {"status": "paid" if paid else "pending", "premium": paid}
