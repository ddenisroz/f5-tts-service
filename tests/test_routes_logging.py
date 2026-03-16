from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.auth import verify_api_key
from app.engine.base import SynthesisResult
from app.main import _make_provider_synthesize_fn
from app.routers import provider, tts_compat


class _DummyPipeline:
    def process(self, text: str, logger=None) -> str:
        return f"{text.strip()}."


class _DummyVoiceStore:
    def __init__(self, ref_audio_path: Path) -> None:
        self._voice = {
            "name": "demo-voice",
            "file_path": str(ref_audio_path),
            "reference_text": "пример референса",
            "cfg_strength": 2.5,
            "speed_preset": "fast",
        }

    async def resolve_voice_record_for_user(self, user_id, requested_voice):
        return dict(self._voice)


class _DummyEngine:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def synthesize(self, **kwargs) -> SynthesisResult:
        self.calls.append(kwargs)
        return SynthesisResult(
            audio_bytes=b"RIFF",
            duration_sec=1.5,
            sample_rate=24000,
            voice=kwargs["voice"],
            meta={"inference_time_sec": 0.25},
        )


class _DummyAudioStore:
    def save_bytes(self, audio_bytes: bytes, suffix: str = ".wav") -> str:
        return f"generated{suffix}"


class _DummyLimitsStore:
    def __init__(self) -> None:
        self.logged: list[dict] = []

    async def validate_request(self, user_id: int, text: str):
        return True, "", {}, {}

    async def log_request(self, user_id: int, *, text_length: int, duration_sec: float | None, success: bool) -> None:
        self.logged.append(
            {
                "user_id": user_id,
                "text_length": text_length,
                "duration_sec": duration_sec,
                "success": success,
            }
        )


def _build_app(tmp_path: Path, *, compat: bool) -> tuple[FastAPI, _DummyEngine, _DummyLimitsStore]:
    voices_dir = tmp_path / "voices"
    voices_dir.mkdir()
    ref_audio = voices_dir / "demo.wav"
    ref_audio.write_bytes(b"stub")

    engine = _DummyEngine()
    limits_store = _DummyLimitsStore()
    app = FastAPI()
    app.dependency_overrides[verify_api_key] = lambda: None
    app.state.settings = SimpleNamespace(
        max_input_text_length=2000,
        limits_enabled=True,
        f5_default_cfg_strength=2.0,
        f5_default_speed_preset="normal",
        f5_default_ref_text="",
        base_path=tmp_path,
    )
    app.state.ru_pipeline = _DummyPipeline()
    app.state.voice_store = _DummyVoiceStore(ref_audio)
    app.state.engine = engine
    app.state.audio_store = _DummyAudioStore()
    app.state.voice_files_dir = voices_dir
    app.state.limits_store = limits_store
    app.state.provider_synthesize = _make_provider_synthesize_fn(app)
    app.include_router(tts_compat.router if compat else provider.router)
    return app, engine, limits_store


def test_provider_route_keeps_response_shape_and_emits_request_logs(workspace_tmp_path, caplog) -> None:
    app, engine, _ = _build_app(workspace_tmp_path, compat=False)
    client = TestClient(app)
    caplog.set_level(logging.INFO)

    response = client.post(
        "/v1/synthesize",
        headers={"Authorization": "Bearer ignored"},
        json={
            "text": "привет мир",
            "voice": "demo-voice",
            "request_id": "req-provider-1",
            "event_id": "evt-provider-1",
            "user_id": 15,
            "channel_name": "provider-demo",
            "author": "tester",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["audio_url"] == "/api/tts/audio/generated.wav"
    assert payload["selected_voice"] == "demo-voice"
    assert engine.calls[0]["metadata"]["request_id"] == "req-provider-1"
    messages = [record.getMessage() for record in caplog.records]
    assert any('request_id="req-provider-1"' in message and "Accepted synthesis request" in message for message in messages)
    assert any('request_id="req-provider-1"' in message and "Synthesis completed" in message for message in messages)


def test_compat_route_keeps_response_shape_and_emits_request_logs(workspace_tmp_path, caplog) -> None:
    app, engine, limits_store = _build_app(workspace_tmp_path, compat=True)
    client = TestClient(app)
    caplog.set_level(logging.INFO)

    response = client.post(
        "/api/tts/synthesize-channel",
        headers={"Authorization": "Bearer ignored"},
        json={
            "channel_name": "compat-demo",
            "text": "привет мир",
            "author": "tester",
            "user_id": 42,
            "voice": "demo-voice",
            "request_id": "req-compat-1",
            "event_id": "evt-compat-1",
            "tts_settings": {},
            "word_filter": [],
            "blocked_users": [],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["success"] is True
    assert payload["audio_url"] == "/api/tts/audio/generated.wav"
    assert payload["selected_voice"] == "demo-voice"
    assert engine.calls[0]["metadata"]["request_id"] == "req-compat-1"
    assert limits_store.logged[0]["user_id"] == 42
    messages = [record.getMessage() for record in caplog.records]
    assert any('request_id="req-compat-1"' in message and "Accepted synthesis request" in message for message in messages)
    assert any('request_id="req-compat-1"' in message and "Synthesis completed" in message for message in messages)
