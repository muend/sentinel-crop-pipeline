"""Layer-2 scene judges: vision-LLM review of scene previews.

Same plugin pattern as DataProvider. Default is Gemini Flash-Lite: free-tier
availability and adequate quality for pass/fail screening. The model id lives
in config (ai_review.model) because Google's lineup and free-tier limits change
often — no quota numbers are hardcoded, 429s are handled with backoff.

Graceful degradation is mandatory: a missing key/SDK, judge_provider: none, or
a failed API call must never stop the pipeline or auto-reject a scene. The
caller (SceneSelector) flags such scenes needs_manual_review and proceeds on
the layer-1 result alone.
"""

import base64
import json
import logging
import os
import time
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass

log = logging.getLogger("judge")

# Config-overridable defaults; verify current names at
# https://ai.google.dev/gemini-api/docs/models and docs.claude.com.
DEFAULT_GEMINI_MODEL = "gemini-3.1-flash-lite"
DEFAULT_CLAUDE_MODEL = "claude-haiku-4-5"

PROMPT = (
    "You are screening a Sentinel-2 RGB preview of an agricultural area for "
    "crop-classification training data. Assess: residual cloud shadow or haze, "
    "visible artifacts, and whether the area looks usable overall. "
    'Reply with JSON only: {"accept": true|false, "confidence": <0.0-1.0>, '
    '"reason": "<one short sentence>"}'
)


class JudgeNotAvailable(RuntimeError):
    """Missing API key or SDK. Callers degrade to layer-1-only selection."""


@dataclass
class JudgeResult:
    accept: bool | None          # None = no verdict
    confidence: float
    reason: str
    provider: str
    needs_manual_review: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


class SceneJudge(ABC):
    name = "base"

    @abstractmethod
    def evaluate(self, scene, preview_image: bytes | None) -> JudgeResult:
        """Judge one scene from its RGB preview (PNG bytes, may be None)."""


def with_backoff(fn, retries: int = 3, backoff: float = 2.0):
    """Retry transient failures (429/5xx/timeouts) with exponential backoff.

    The last exception propagates; the caller converts it to
    needs_manual_review instead of failing the run.
    """
    for attempt in range(retries + 1):
        try:
            return fn()
        except Exception:
            if attempt == retries:
                raise
            time.sleep(backoff ** attempt)


def parse_verdict(text: str, provider: str) -> JudgeResult:
    try:
        data = json.loads(text[text.index("{"): text.rindex("}") + 1])
        return JudgeResult(
            accept=bool(data["accept"]),
            confidence=max(0.0, min(1.0, float(data.get("confidence", 0.5)))),
            reason=str(data.get("reason", "")),
            provider=provider,
        )
    except (ValueError, KeyError, TypeError) as exc:
        return JudgeResult(None, 0.0, f"unparseable judge reply: {exc}",
                           provider, needs_manual_review=True)


class GeminiFlashJudge(SceneJudge):
    name = "gemini"

    def __init__(self, model: str = DEFAULT_GEMINI_MODEL, api_key: str | None = None):
        api_key = (api_key or os.environ.get("GEMINI_API_KEY")
                   or os.environ.get("GOOGLE_API_KEY"))
        if not api_key:
            raise JudgeNotAvailable("GEMINI_API_KEY not set (see .env.example)")
        try:
            from google import genai
        except ImportError as exc:
            raise JudgeNotAvailable(
                "google-genai not installed; "
                "pip install 'sentinel-crop-pipeline[ai]'") from exc
        self.client = genai.Client(api_key=api_key)
        self.model = model

    def evaluate(self, scene, preview_image: bytes | None) -> JudgeResult:
        from google.genai import types

        contents = [f"{PROMPT}\nScene: {scene.id} acquired {scene.datetime}"]
        if preview_image:
            contents.append(types.Part.from_bytes(data=preview_image,
                                                  mime_type="image/png"))
        resp = with_backoff(lambda: self.client.models.generate_content(
            model=self.model, contents=contents))
        return parse_verdict(resp.text or "", self.name)


class ClaudeJudge(SceneJudge):
    name = "claude"

    def __init__(self, model: str = DEFAULT_CLAUDE_MODEL, api_key: str | None = None):
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise JudgeNotAvailable("ANTHROPIC_API_KEY not set (see .env.example)")
        try:
            import anthropic
        except ImportError as exc:
            raise JudgeNotAvailable(
                "anthropic not installed; "
                "pip install 'sentinel-crop-pipeline[claude]'") from exc
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    def evaluate(self, scene, preview_image: bytes | None) -> JudgeResult:
        content: list[dict] = [
            {"type": "text",
             "text": f"{PROMPT}\nScene: {scene.id} acquired {scene.datetime}"}]
        if preview_image:
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/png",
                           "data": base64.b64encode(preview_image).decode()},
            })
        resp = with_backoff(lambda: self.client.messages.create(
            model=self.model, max_tokens=200,
            messages=[{"role": "user", "content": content}]))
        text = "".join(b.text for b in resp.content if hasattr(b, "text"))
        return parse_verdict(text, self.name)


def get_judge(cfg: dict) -> SceneJudge | None:
    """Build the configured judge, or None (layer-1-only) when disabled or
    unavailable. Never raises for missing keys/SDKs."""
    jcfg = cfg.get("ai_review", {})
    provider = str(jcfg.get("judge_provider", "none")).lower()
    if provider in ("", "none"):
        return None
    try:
        if provider == "gemini":
            return GeminiFlashJudge(model=jcfg.get("model", DEFAULT_GEMINI_MODEL))
        if provider == "claude":
            return ClaudeJudge(model=jcfg.get("claude_model", DEFAULT_CLAUDE_MODEL))
    except JudgeNotAvailable as exc:
        log.warning("judge '%s' unavailable (%s); scenes will be flagged "
                    "needs_manual_review", provider, exc)
        return None
    raise ValueError(f"Unknown judge_provider '{provider}' (gemini | claude | none)")
