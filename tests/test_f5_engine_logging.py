from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import numpy as np
import pytest

from app.engine.f5_engine import F5Engine


class _FakeModel:
    def __init__(self, *, fail_first_cuda: bool = False) -> None:
        self.fail_first_cuda = fail_first_cuda
        self.calls: list[dict] = []

    def infer(self, **kwargs):
        self.calls.append(dict(kwargs))
        kwargs["show_info"]("Converting audio...")
        for _ in kwargs["progress"].tqdm([1, 2], desc="batch", total=2):
            pass
        if self.fail_first_cuda and len(self.calls) == 1:
            raise RuntimeError("CUDA error: out of memory")
        return np.full(2400, 0.5, dtype=np.float32), 24000, None


def _build_engine(tmp_path: Path, model: _FakeModel | None = None) -> F5Engine:
    vocoder_dir = tmp_path / "vocoder"
    vocoder_dir.mkdir(parents=True, exist_ok=True)
    engine = F5Engine(
        mode="real",
        upstream_dir=tmp_path,
        russian_weights_dir=tmp_path,
        model_name="F5TTS_v1_Base",
        checkpoint_file="",
        vocab_file="",
        hf_cache_dir=tmp_path,
        vocoder_local_dir=vocoder_dir,
        vocoder_repo_id="charactr/vocos-mel-24khz",
        device="cpu",
        ode_method="euler",
        use_ema=True,
        target_rms=0.1,
        cross_fade_duration=0.15,
        nfe_step=32,
        sway_sampling_coef=-1.0,
        default_cfg_strength=2.0,
        default_speed_preset="normal",
    )
    engine._ready = True
    engine._model = model or _FakeModel()
    return engine


def test_f5_engine_logs_upstream_messages_and_progress(workspace_tmp_path, caplog) -> None:
    engine = _build_engine(workspace_tmp_path)
    ref_audio = workspace_tmp_path / "ref.wav"
    ref_audio.write_bytes(b"stub")

    caplog.set_level(logging.INFO)

    result = asyncio.run(
        engine.synthesize(
            text="тест",
            voice="demo",
            ref_audio_path=str(ref_audio),
            ref_text="пример",
            metadata={
                "request_id": "req-engine-1",
                "event_id": "evt-engine-1",
                "channel_name": "demo-channel",
                "user_id": 77,
            },
        )
    )

    assert result.sample_rate == 24000
    assert result.duration_sec > 0
    messages = [record.getMessage() for record in caplog.records]
    assert any('request_id="req-engine-1"' in message and "F5 upstream: Converting audio..." in message for message in messages)
    assert any('request_id="req-engine-1"' in message and "Inference progress started" in message for message in messages)
    assert any('request_id="req-engine-1"' in message and "Inference progress completed" in message for message in messages)


def test_f5_engine_restores_legacy_adaptive_speed_and_nfe(workspace_tmp_path) -> None:
    model = _FakeModel()
    engine = _build_engine(workspace_tmp_path, model=model)
    ref_audio = workspace_tmp_path / "ref.wav"
    ref_audio.write_bytes(b"stub")

    result = asyncio.run(
        engine.synthesize(
            text="\u0434\u0430",
            voice="demo",
            ref_audio_path=str(ref_audio),
            ref_text="\u043f\u0440\u0438\u043c\u0435\u0440",
            speed_preset="normal",
        )
    )

    assert len(model.calls) == 1
    assert model.calls[0]["speed"] == pytest.approx(0.5)
    assert model.calls[0]["nfe_step"] == 26
    assert result.meta["detected_language"] == "russian"
    assert result.meta["text_length_no_spaces"] == 2
    assert result.meta["nfe_step"] == 26
    assert result.meta["speed_factor"] == pytest.approx(0.5)
    assert result.duration_sec > 0.95


def test_f5_engine_uses_long_text_legacy_heuristics(workspace_tmp_path) -> None:
    model = _FakeModel()
    engine = _build_engine(workspace_tmp_path, model=model)
    ref_audio = workspace_tmp_path / "ref.wav"
    ref_audio.write_bytes(b"stub")
    long_text = "\u0430" * 130

    result = asyncio.run(
        engine.synthesize(
            text=long_text,
            voice="demo",
            ref_audio_path=str(ref_audio),
            ref_text="\u043f\u0440\u0438\u043c\u0435\u0440",
            speed_preset="fast",
        )
    )

    assert len(model.calls) == 1
    assert model.calls[0]["speed"] == pytest.approx(1.5)
    assert model.calls[0]["nfe_step"] == 18
    assert result.meta["text_length_no_spaces"] == 130
    assert result.meta["nfe_step"] == 18
    assert result.meta["speed_factor"] == pytest.approx(1.5)


def test_f5_engine_retries_cuda_failure_with_legacy_fallback(workspace_tmp_path, caplog) -> None:
    model = _FakeModel(fail_first_cuda=True)
    engine = _build_engine(workspace_tmp_path, model=model)
    ref_audio = workspace_tmp_path / "ref.wav"
    ref_audio.write_bytes(b"stub")

    caplog.set_level(logging.INFO)

    result = asyncio.run(
        engine.synthesize(
            text="\u0434\u0430",
            voice="demo",
            ref_audio_path=str(ref_audio),
            ref_text="\u043f\u0440\u0438\u043c\u0435\u0440",
            speed_preset="normal",
            metadata={"request_id": "req-engine-fallback"},
        )
    )

    assert len(model.calls) == 2
    assert model.calls[0]["speed"] == pytest.approx(0.5)
    assert model.calls[0]["nfe_step"] == 26
    assert model.calls[1]["speed"] == pytest.approx(1.0)
    assert model.calls[1]["nfe_step"] == 16
    assert result.meta["speed_factor"] == pytest.approx(1.0)
    assert result.meta["nfe_step"] == 16
    messages = [record.getMessage() for record in caplog.records]
    assert any("CUDA inference failed; retrying with legacy fallback" in message for message in messages)
