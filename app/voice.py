from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from app.config import WHISPER_MODEL_PATH


def transcribe_audio_bytes(audio_bytes: bytes | Any, language: str | None = None) -> str:
    if not audio_bytes:
        return ""

    try:
        from faster_whisper import WhisperModel
    except Exception:
        return ""

    try:
        raw = audio_bytes.getvalue() if hasattr(audio_bytes, "getvalue") else audio_bytes
    except Exception:
        raw = audio_bytes

    if not raw:
        return ""

    model_path = Path(WHISPER_MODEL_PATH) if WHISPER_MODEL_PATH else None
    if model_path is None or not model_path.exists():
        return ""

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
            handle.write(raw)
            temp_path = Path(handle.name)

        model = WhisperModel(str(model_path), device="cpu", compute_type="int8", local_files_only=True)
        segments, _ = model.transcribe(str(temp_path), language=language)
        transcript = " ".join(segment.text for segment in segments).strip()
        return transcript
    except Exception:
        return ""
    finally:
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink(missing_ok=True)
            except Exception:
                pass
