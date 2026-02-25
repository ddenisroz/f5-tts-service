from __future__ import annotations

import re
import subprocess
from pathlib import Path


ALLOWED_AUDIO_EXTENSIONS = {".wav", ".mp3", ".ogg", ".flac", ".m4a", ".aac", ".wma", ".aiff", ".au"}
VOICE_NAME_RE = re.compile(r"^[0-9A-Za-z\u0400-\u04FF _-]{1,80}$")


def sanitize_voice_name(raw_name: str) -> str:
    normalized = (raw_name or "").strip()
    if not VOICE_NAME_RE.fullmatch(normalized):
        raise ValueError("Invalid voice name")
    return normalized


def ensure_allowed_audio_extension(filename: str) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in ALLOWED_AUDIO_EXTENSIONS:
        raise ValueError(
            f"Unsupported audio format '{suffix}'. Allowed: {', '.join(sorted(ALLOWED_AUDIO_EXTENSIONS))}"
        )
    return suffix


def has_valid_audio_signature(path: Path) -> bool:
    try:
        with path.open("rb") as handle:
            header = handle.read(16)
    except Exception:
        return False
    if len(header) < 4:
        return False

    if header.startswith(b"RIFF") and len(header) >= 12 and header[8:12] == b"WAVE":
        return True
    if header.startswith(b"ID3") or (header[0] == 0xFF and (header[1] & 0xE0) == 0xE0):
        return True
    if header.startswith(b"OggS"):
        return True
    if header.startswith(b"fLaC"):
        return True
    if len(header) >= 12 and header[4:8] == b"ftyp":
        return True
    if header.startswith(bytes.fromhex("3026B2758E66CF11")):
        return True
    if header.startswith(b"FORM") and len(header) >= 12 and header[8:12] in {b"AIFF", b"AIFC"}:
        return True
    if header.startswith(b".snd"):
        return True
    return False


def convert_audio_to_wav(input_path: Path, output_path: Path, *, sample_rate: int = 24000, channels: int = 1) -> None:
    errors: list[str] = []

    ffmpeg_cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(input_path),
        "-ar",
        str(sample_rate),
        "-ac",
        str(channels),
        "-sample_fmt",
        "s16",
        str(output_path),
    ]
    try:
        result = subprocess.run(ffmpeg_cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0 and output_path.exists():
            return
        errors.append(f"ffmpeg failed: {result.stderr.strip() or result.stdout.strip()}")
    except Exception as error:
        errors.append(f"ffmpeg execution failed: {error}")

    try:
        from pydub import AudioSegment

        audio = AudioSegment.from_file(str(input_path))
        audio = audio.set_frame_rate(sample_rate).set_channels(channels).set_sample_width(2)
        audio.export(str(output_path), format="wav")
        if output_path.exists():
            return
        errors.append("pydub export did not create output file")
    except Exception as error:
        errors.append(f"pydub conversion failed: {error}")

    raise RuntimeError("; ".join(errors))


def get_audio_duration_sec(path: Path) -> float:
    errors: list[str] = []

    ffprobe_cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    try:
        result = subprocess.run(ffprobe_cmd, capture_output=True, text=True, check=False)
        if result.returncode == 0:
            raw = (result.stdout or "").strip()
            if raw:
                value = float(raw)
                if value >= 0:
                    return value
        errors.append(f"ffprobe failed: {result.stderr.strip() or result.stdout.strip()}")
    except Exception as error:
        errors.append(f"ffprobe execution failed: {error}")

    try:
        from pydub import AudioSegment

        audio = AudioSegment.from_file(str(path))
        return max(0.0, float(audio.duration_seconds))
    except Exception as error:
        errors.append(f"pydub duration failed: {error}")

    raise RuntimeError("; ".join(errors))
