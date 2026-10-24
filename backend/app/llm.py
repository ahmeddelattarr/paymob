from google import genai
from google.genai import types

from . import config


class LLMError(Exception):
    pass


_client = (genai.Client(api_key=config.GEMINI_API_KEY,
                        http_options=types.HttpOptions(timeout=int(config.LLM_TIMEOUT * 1000)))
           if config.GEMINI_API_KEY else None)


def available() -> bool:
    return _client is not None


def structured(prompt: str, output_model, *, system: str = "", fast: bool = False):
    """One structured-output call. Raises LLMError on any failure so callers can fall back."""
    if not _client:
        raise LLMError("LLM not configured")
    try:
        r = _client.models.generate_content(
            model=config.LLM_FAST_MODEL if fast else config.LLM_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=system or "You are a precise career-readiness assistant for tech graduates in Egypt.",
                response_mime_type="application/json",
                response_schema=output_model,
                temperature=0,
            ),
        )
    except Exception as e:  # any SDK/network/timeout error -> caller's deterministic fallback
        raise LLMError(str(e)) from e
    if not isinstance(r.parsed, output_model):
        raise LLMError(f"no structured output (finish_reason={r.candidates[0].finish_reason if r.candidates else None})")
    return r.parsed
