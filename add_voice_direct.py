#!/usr/bin/env python3
"""Add or update a global voice entry in the F5_tts database."""

from __future__ import annotations

import argparse
from pathlib import Path

from config import config
from database import SessionLocal, Voice as VoiceModel


def _resolve_voice_path(raw_path: str) -> Path:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = config.base_dir / candidate
    return candidate.resolve()


def add_voice(name: str, file_path: str, reference_text: str | None = None, public: bool = True) -> bool:
    resolved_file = _resolve_voice_path(file_path)
    if not resolved_file.exists():
        print(f"[ERROR] Voice file not found: {resolved_file}")
        return False

    db = SessionLocal()
    try:
        existing = db.query(VoiceModel).filter(VoiceModel.name == name).first()
        if existing:
            print(f"[WARN] Voice '{name}' already exists (id={existing.id}).")
            return False

        # Keep relative path storage when file is under service root.
        try:
            stored_path = str(resolved_file.relative_to(config.base_dir))
        except ValueError:
            stored_path = str(resolved_file)

        voice = VoiceModel(
            name=name,
            voice_type="global",
            file_path=stored_path,
            reference_text=reference_text,
            owner_id=None,
            is_public=public,
            is_active=True,
            is_global=True,
            cfg_strength=config.cfg_strength,
            speed_preset="normal",
            cross_fade_duration=0.15,
            silence_duration_ms=100,
            sway_sampling_coef=-1.0,
        )

        db.add(voice)
        db.commit()
        db.refresh(voice)

        print(f"[OK] Added voice '{voice.name}' (id={voice.id})")
        print(f"     file_path={voice.file_path}")
        return True
    except Exception as exc:
        db.rollback()
        print(f"[ERROR] Failed to add voice: {exc}")
        return False
    finally:
        db.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Add global voice into F5_tts DB")
    parser.add_argument("name", help="Voice name")
    parser.add_argument("file_path", help="Path to voice file (absolute or relative to F5_tts)")
    parser.add_argument("--reference-text", default=None, help="Optional reference text")
    parser.add_argument("--private", action="store_true", help="Set is_public=false")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    success = add_voice(
        name=args.name,
        file_path=args.file_path,
        reference_text=args.reference_text,
        public=not args.private,
    )
    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
