import anthropic

from . import config


class LLMError(Exception):
    pass


_client = (anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY, timeout=config.LLM_TIMEOUT, max_retries=1)
           if config.ANTHROPIC_API_KEY else None)


def available() -> bool:
    return _client is not None


def structured(prompt: str, output_model, *, system: str = "", fast: bool = False):
    """One structured-output call. Raises LLMError on any failure so callers can fall back."""
    if not _client:
        raise LLMError("LLM not configured")
    try:
        r = _client.messages.parse(
            model=config.LLM_FAST_MODEL if fast else config.LLM_MODEL,
            max_tokens=8000,
            system=system or "You are a precise career-readiness assistant for tech graduates in Egypt.",
            messages=[{"role": "user", "content": prompt}],
            output_config={"effort": "low"},
            output_format=output_model,
        )
    except anthropic.APIError as e:
        raise LLMError(str(e)) from e
    if r.parsed_output is None:
        raise LLMError(f"no structured output (stop_reason={r.stop_reason})")
    return r.parsed_output
