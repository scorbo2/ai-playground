"""
FastAPI REST server for Qwen3-TTS voice cloning.

Loads the model once on startup, then exposes a single POST endpoint for
synthesis.  Clients send text, a reference audio sample (base64), and the
transcript of that sample.  The server returns the generated audio as
base64-encoded WAV.

Usage:
    uvicorn apps.rest_api.server:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import base64
import io
import math
import random
import uuid
from pathlib import Path
from typing import Any, NamedTuple

import soundfile as sf  # noqa: E402
import torch  # noqa: E402
from fastapi import FastAPI, HTTPException  # noqa: E402
from fastapi.responses import HTMLResponse  # noqa: E402
from fastapi.responses import JSONResponse  # noqa: E402
from loguru import logger  # noqa: E402
from pydantic import BaseModel, Field, field_validator  # noqa: E402
from qwen_tts import Qwen3TTSModel  # noqa: E402
from typing_extensions import Literal  # noqa: E402


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# You can specify a huggingface id, like ""Qwen/Qwen3-TTS-12Hz-1.7B-Base"",
# or a local path, like "/home/user/myModes/Qwen3-TTS-Base/"
MODEL_NAME_OR_PATH = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"

SEED_MIN = 1
SEED_MAX = 1000


class Runtime(NamedTuple):
    """Holds the loaded model instance."""
    model: Qwen3TTSModel


# Global — lazily initialised on first request or at startup.
_runtime: Runtime | None = None

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class SynthesisRequest(BaseModel):
    """A single synthesis request."""

    text: str = Field(..., description="Text to synthesize, e.g. 'Hello there'")
    audio_base64: str = Field(
        ...,
        description=(
            "Reference audio sample (~10 s WAV) encoded as a base64 string. "
            "The server will decode this to a temporary WAV file before synthesis."
        ),
    )
    prompt_text: str = Field(
        ...,
        description=(
            "Exact transcript of the reference audio, e.g. "
            "'Hello, my name is Alice, nice to meet you'."
        ),
    )

    # Optional overrides (defaults are sensible for voice cloning)
    seed: int | None = Field(
        None,
        ge=SEED_MIN,
        le=SEED_MAX,
        description=(
            "Random seed for reproducibility.  If omitted, a random seed "
            f"in [{SEED_MIN}, {SEED_MAX}] is chosen."
        ),
    )
    language: str | None = Field(
        None,
        description=(
            "Language of the text to synthesize (e.g. 'English', 'Chinese', "
            "'Japanese').  Omit or pass 'Auto' for auto-detection."
        ),
    )


class SynthesisResponse(BaseModel):
    """The synthesis result."""

    audio_base64: str = Field(
        ...,
        description="Generated WAV audio encoded as a base64 string.",
    )
    sample_rate: int = Field(..., description="Audio sample rate (Hz).")
    seed: int = Field(..., description="Seed used for this generation.")
    time_used: float = Field(
        ..., description="Wall-clock generation time in seconds."
    )
    rtf: float | None = Field(
        ...,
        description=(
            "Real-time factor (time / audio duration).  "
            "null when audio duration is zero."
        ),
    )

    @field_validator("rtf", mode="before")
    @classmethod
    def _sanitize_rtf(cls, v: float | None) -> float | None:
        """Replace inf / nan with None so JSON serialization never fails."""
        if v is None:
            return None
        if math.isinf(v) or math.isnan(v):
            return None
        return v

    @field_validator("time_used", mode="before")
    @classmethod
    def _sanitize_time_used(cls, v: float | None) -> float | None:
        """Guard against inf / nan in time_used as well."""
        if v is None:
            return None
        if math.isinf(v) or math.isnan(v):
            return 0.0
        return v


class HealthResponse(BaseModel):
    """Health / readiness check."""

    status: Literal["ok"] = "ok"
    model: str = MODEL_NAME_OR_PATH
    serverType: str = "Qwen3-TTS"


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Qwen3-TTS Voice Cloning API",
    description=(
        "REST API around Qwen3-TTS.  Send text + a reference audio sample "
        "and get back cloned speech."
    ),
    version="0.1.0",
)

# ---------------------------------------------------------------------------
# Lazy model loading — loaded on first request (or explicitly via startup).
# ---------------------------------------------------------------------------

def _get_runtime() -> Runtime:
    """Return the global runtime, loading the model once if necessary.

    The model is loaded in bfloat16 with Flash Attention 2 for best
    performance.  If Flash Attention 2 is unavailable, it falls back
    to the default attention implementation.
    """
    global _runtime
    if _runtime is not None:
        return _runtime

    logger.info("Loading Qwen3-TTS model '{}' on CUDA ...", MODEL_NAME_OR_PATH)

    attn_impl = "flash_attention_2"
    try:
        model = Qwen3TTSModel.from_pretrained(
            MODEL_NAME_OR_PATH,
            device_map="cuda:0",
            dtype=torch.bfloat16,
            attn_implementation=attn_impl,
        )
    except Exception:
        logger.warning(
            "Flash Attention 2 unavailable; falling back to default attention."
        )
        model = Qwen3TTSModel.from_pretrained(
            MODEL_NAME_OR_PATH,
            device_map="cuda:0",
            dtype=torch.bfloat16,
        )

    _runtime = Runtime(model=model)
    logger.info("Model loaded successfully.")
    return _runtime


# ---------------------------------------------------------------------------
# Global exception handler — catches anything that slips past endpoint handlers
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def _unhandled_exception(
    _request, exc: Exception
) -> JSONResponse:
    """Return a meaningful 500 instead of FastAPI's blank ``detail: ''``."""
    logger.error("Unhandled exception: {}", exc, exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": f"Internal server error: {exc}"},
    )


# ---------------------------------------------------------------------------
# Startup / shutdown hooks
# ---------------------------------------------------------------------------


@app.on_event("startup")
def startup() -> None:
    """Pre-load the model so the first request is fast."""
    _get_runtime()


@app.on_event("shutdown")
def shutdown() -> None:
    """Clean up GPU resources."""
    global _runtime
    _runtime = None  # Drop the only reference; GC + PyTorch will free the model.
    torch.cuda.empty_cache()
    logger.info("Model unloaded and CUDA cache cleared.")


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse, tags=["System"])
def root() -> str:
    """A friendly landing page so browser visitors don't get the auto-generated docs."""
    return """
    <!DOCTYPE html>
    <html>
    <head><title>Qwen3-TTS REST API</title></head>
    <body>
        <h1>Qwen3-TTS Voice Cloning REST API</h1>
        <p>This server is configured and running. It is a REST API, not a web server.</p>
        <p>Use a REST client like <strong>Postman</strong>, <strong>Insomnia</strong>,
        or <strong>curl</strong> to make requests.</p>
        <ul>
            <li><code>GET /health</code> &mdash; Check server status</li>
            <li><code>POST /synthesize</code> &mdash; Generate cloned speech</li>
        </ul>
    </body>
    </html>
    """

@app.get("/health", response_model=HealthResponse, tags=["System"])
def health() -> HealthResponse:
    """Check whether the server is alive and the model is loaded."""
    model_loaded = _runtime is not None
    if not model_loaded:
        logger.warning("Health check: model not yet loaded.")
    return HealthResponse()


@app.post(
    "/synthesize",
    response_model=SynthesisResponse,
    tags=["Synthesis"],
    summary="Synthesize speech from text + reference audio",
)
def synthesize(req: SynthesisRequest) -> SynthesisResponse:
    """
    Synthesize audio using the provided text and reference audio sample.

    The Qwen3-TTS Base model performs zero-shot voice cloning: it takes a
    short reference audio clip and its transcript, then generates new speech
    in the same voice.
    """
    runtime = _get_runtime()

    # Resolve randomised seed for reproducibility.
    seed = req.seed if req.seed is not None else random.randint(SEED_MIN, SEED_MAX)
    torch.manual_seed(seed)

    # TalkWithMe sends up a two-letter language code like "en" or "fr",
    # but Qwen wants a full language name like "English" or "French".
    # We could translate this here, but I actually find just using "auto"
    # seems to work without issue, even with multi-lingual personas.
    #language = req.language if req.language else "Auto"
    language = "auto" # just hard-code it

    logger.info(
        "Synthesizing: seed={}, text_len={}, lang={}",
        seed,
        len(req.text),
        language,
    )

    # Decode the base64 audio and write to a temporary file.
    try:
        raw_audio = base64.b64decode(req.audio_base64)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid base64 audio: {exc}")

    prompt_audio_path = _write_temp_wav(raw_audio)

    try:
        # generate_voice_clone returns (wavs, sr) where wavs is a numpy array
        # of shape (batch, samples) and sr is the sample rate.
        start_time = torch.cuda.Event(enable_timing=True)
        end_time = torch.cuda.Event(enable_timing=True)
        start_time.record()

        wavs, sr = runtime.model.generate_voice_clone(
            text=req.text,
            language=language,
            ref_audio=prompt_audio_path,
            ref_text=req.prompt_text,
        )

        end_time.record()
        torch.cuda.synchronize()
        elapsed_ms = start_time.elapsed_time(end_time)
        time_used = elapsed_ms / 1000.0

        # wavs[0] is the generated waveform (1-D numpy array, float32).
        wav = wavs[0]
        audio_duration = len(wav) / sr if sr else 0
        rtf = time_used / audio_duration if audio_duration > 0 else None

        audio_bytes = _numpy_to_wav_bytes(wav, sr)
        audio_b64 = base64.b64encode(audio_bytes).decode("ascii")

        return SynthesisResponse(
            audio_base64=audio_b64,
            sample_rate=sr,
            seed=seed,
            time_used=time_used,
            rtf=rtf,
        )

    except Exception as exc:
        logger.error("Synthesis failed: {}", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        # Clean up the temporary prompt audio file.
        _cleanup_temp(prompt_audio_path)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TEMP_AUDIO_DIR = Path("/tmp/qwen3_tts_rest_api")
_TEMP_AUDIO_DIR.mkdir(exist_ok=True)


def _write_temp_wav(raw_bytes: bytes) -> str:
    """
    Write raw audio bytes to a temporary WAV file.

    The input is expected to be a valid WAV file (just bytes).  We write it
    directly to disk because the model's ref_audio parameter accepts file paths.
    """
    path = _TEMP_AUDIO_DIR / f"{uuid.uuid4().hex}.wav"
    path.write_bytes(raw_bytes)
    logger.debug("Wrote temporary prompt audio: {}", path)
    return str(path)


def _cleanup_temp(path: str) -> None:
    """Remove a temporary audio file if it exists."""
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


def _numpy_to_wav_bytes(audio_array: Any, sample_rate: int) -> bytes:
    """
    Convert a numpy audio array to WAV-encoded bytes.

    Qwen3TTSModel.generate_voice_clone returns numpy arrays (not tensors),
    so we use this helper instead of a tensor-based one.
    """
    buffer = io.BytesIO()
    sf.write(
        buffer,
        audio_array,
        sample_rate,
        format="WAV",
        subtype="PCM_16",
    )
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Main (for running directly: python -m apps.rest_api.server)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn

    logger.info("Starting Qwen3-TTS REST API server on 0.0.0.0:8000")
    uvicorn.run(
        "apps.rest_api.server:app",
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
