from __future__ import annotations

import asyncio
import logging
import os
import re
import shutil
import tempfile
import uuid
from pathlib import Path

from fastapi import UploadFile

from .audio_processing import (
    convert_audio_to_wav,
    ensure_allowed_audio_extension,
    get_audio_duration_sec,
    has_valid_audio_signature,
)

FILENAME_PART_RE = re.compile(r"[^0-9A-Za-z\u0400-\u04FF_-]+")
logger = logging.getLogger(__name__)
UPLOAD_CHUNK_SIZE = 1024 * 1024


def _create_temp_path(*, suffix: str) -> Path:
    fd, name = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    return Path(name)


def _safe_filename_part(raw: str) -> str:
    normalized = FILENAME_PART_RE.sub("_", (raw or "").strip()).strip("_")
    return normalized[:64] or "voice"


async def transcribe_voice_file(app, voice_path: Path) -> str:
    if not voice_path.exists():
        raise ValueError(f"Voice file not found: {voice_path}")
    transcriber = app.state.transcriber
    if not transcriber.enabled:
        return ""
    return await transcriber.transcribe(voice_path)


async def prepare_uploaded_voice_file(
    app,
    *,
    upload: UploadFile,
    filename_prefix: str,
) -> tuple[Path, str]:
    suffix = ensure_allowed_audio_extension(upload.filename or "")
    temp_input = _create_temp_path(suffix=suffix)
    temp_wav = _create_temp_path(suffix=".wav")
    try:
        max_bytes = max(1_000_000, int(app.state.settings.voice_upload_max_bytes))
        total_bytes = 0
        with temp_input.open("wb") as handle:
            while True:
                chunk = await upload.read(UPLOAD_CHUNK_SIZE)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > max_bytes:
                    raise ValueError(f"Uploaded audio is too large. Maximum {max_bytes} bytes")
                handle.write(chunk)
        if total_bytes == 0:
            raise ValueError("Uploaded audio file is empty")

        if not has_valid_audio_signature(temp_input):
            raise ValueError("Invalid audio file signature")

        sample_rate = int(app.state.settings.voice_upload_sample_rate)
        await asyncio.to_thread(convert_audio_to_wav, temp_input, temp_wav, sample_rate=sample_rate, channels=1)
        duration_sec = await asyncio.to_thread(get_audio_duration_sec, temp_wav)
        min_duration = max(0.1, float(app.state.settings.voice_upload_min_duration_sec))
        max_duration = max(min_duration, float(app.state.settings.voice_upload_max_duration_sec))
        if duration_sec < min_duration:
            raise ValueError(f"Voice sample is too short. Minimum {min_duration:.2f}s")
        if duration_sec > max_duration:
            raise ValueError(f"Voice sample is too long. Maximum {max_duration:.2f}s")

        safe_prefix = _safe_filename_part(filename_prefix)
        target_name = f"{safe_prefix}_{uuid.uuid4().hex}.wav"
        target_path = app.state.voice_files_dir / target_name
        await asyncio.to_thread(shutil.copy2, temp_wav, target_path)

        try:
            reference_text = await transcribe_voice_file(app, target_path)
        except Exception as error:
            logger.warning("Voice transcription failed; keeping empty reference_text: %s", error)
            reference_text = ""
        return target_path, reference_text
    finally:
        await upload.close()
        if temp_input.exists():
            temp_input.unlink(missing_ok=True)
        if temp_wav.exists():
            temp_wav.unlink(missing_ok=True)
