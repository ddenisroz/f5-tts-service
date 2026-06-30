from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import numpy as np
import pytest

from app.engine import f5_engine as f5_engine_module
from app.engine.f5_engine import F5Engine, MISHA_RUSSIAN_CHECKPOINT_FILE


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


class _ReferenceAudioRetryModel:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def infer(self, **kwargs):
        self.calls.append(dict(kwargs))
        if len(self.calls) == 1:
            raise RuntimeError("Failed to open input file")
        return np.full(2400, 0.5, dtype=np.float32), 24000, None


def test_f5_engine_installs_inference_only_trainer_stub(monkeypatch) -> None:
    monkeypatch.delitem(sys.modules, f5_engine_module.TRAINER_MODULE_NAME, raising=False)

    F5Engine._install_inference_trainer_stub()

    trainer_module = sys.modules[f5_engine_module.TRAINER_MODULE_NAME]
    with pytest.raises(RuntimeError, match="inference service runtime"):
        trainer_module.Trainer()


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


def _build_fake_engine(tmp_path: Path) -> F5Engine:
    vocoder_dir = tmp_path / "vocoder"
    vocoder_dir.mkdir(parents=True, exist_ok=True)
    return F5Engine(
        mode="fake",
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


def test_f5_engine_prefers_misha_checkpoint(workspace_tmp_path) -> None:
    misha_checkpoint = workspace_tmp_path / MISHA_RUSSIAN_CHECKPOINT_FILE
    fallback_checkpoint = workspace_tmp_path / "model_last_inference.safetensors"
    misha_checkpoint.write_bytes(b"misha")
    fallback_checkpoint.write_bytes(b"fallback")
    (workspace_tmp_path / "vocab.txt").write_text("а\n", encoding="utf-8")

    engine = _build_engine(workspace_tmp_path)

    assert Path(engine._resolve_checkpoint_file()) == misha_checkpoint.resolve()


def test_f5_engine_fake_mode_is_ready_without_real_model(workspace_tmp_path, caplog) -> None:
    engine = _build_fake_engine(workspace_tmp_path)
    caplog.set_level(logging.INFO)

    assert engine.ready is True
    asyncio.run(engine.prewarm())

    messages = [record.getMessage() for record in caplog.records]
    assert any("F5 fake engine is ready" in message for message in messages)


def test_f5_engine_fake_mode_can_synthesize_without_reference_audio(workspace_tmp_path) -> None:
    engine = _build_fake_engine(workspace_tmp_path)

    result = asyncio.run(
        engine.synthesize(
            text="hello мир",
            voice="demo",
            ref_audio_path=str(workspace_tmp_path / "missing.wav"),
            ref_text="",
            speed_preset="fast",
        )
    )

    assert result.sample_rate == 24000
    assert result.duration_sec > 0.5
    assert result.audio_bytes.startswith(b"RIFF")
    assert result.meta["engine_mode"] == "fake"
    assert result.meta["fake_mode"] is True


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
    assert model.calls[0]["speed"] == pytest.approx(0.9)
    assert model.calls[0]["nfe_step"] == 26
    assert result.meta["detected_language"] == "russian"
    assert result.meta["text_length_no_spaces"] == 2
    assert result.meta["nfe_step"] == 26
    assert result.meta["speed_factor"] == pytest.approx(0.9)
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
    assert model.calls[0]["speed"] == pytest.approx(1.42)
    assert model.calls[0]["nfe_step"] == 18
    assert result.meta["text_length_no_spaces"] == 130
    assert result.meta["nfe_step"] == 18
    assert result.meta["speed_factor"] == pytest.approx(1.42)


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
    assert model.calls[0]["speed"] == pytest.approx(0.9)
    assert model.calls[0]["nfe_step"] == 26
    assert model.calls[1]["speed"] == pytest.approx(1.0)
    assert model.calls[1]["nfe_step"] == 16
    assert result.meta["speed_factor"] == pytest.approx(1.0)
    assert result.meta["nfe_step"] == 16
    messages = [record.getMessage() for record in caplog.records]
    assert any("CUDA inference failed; retrying with legacy fallback" in message for message in messages)


def test_f5_engine_retries_with_normalized_reference_audio(workspace_tmp_path, monkeypatch, caplog) -> None:
    model = _ReferenceAudioRetryModel()
    engine = _build_engine(workspace_tmp_path, model=model)
    ref_audio = workspace_tmp_path / "ref.wav"
    ref_audio.write_bytes(b"stub")

    converted_pairs: list[tuple[Path, Path]] = []

    def _fake_convert_audio_to_wav(input_path: Path, output_path: Path, *, sample_rate: int = 24000, channels: int = 1) -> None:
        converted_pairs.append((Path(input_path), Path(output_path)))
        assert sample_rate == 24000
        assert channels == 1
        Path(output_path).write_bytes(b"RIFFstubWAVE")

    monkeypatch.setattr(f5_engine_module, "convert_audio_to_wav", _fake_convert_audio_to_wav)
    caplog.set_level(logging.INFO)

    result = asyncio.run(
        engine.synthesize(
            text="да",
            voice="demo",
            ref_audio_path=str(ref_audio),
            ref_text="пример",
            metadata={"request_id": "req-engine-audio-retry"},
        )
    )

    assert result.sample_rate == 24000
    assert len(model.calls) == 2
    assert model.calls[0]["ref_file"] == str(ref_audio.resolve())
    assert model.calls[1]["ref_file"] != str(ref_audio.resolve())
    assert Path(model.calls[1]["ref_file"]).suffix == ".wav"
    assert not Path(model.calls[1]["ref_file"]).exists()
    assert converted_pairs == [(ref_audio.resolve(), Path(model.calls[1]["ref_file"]))]
    messages = [record.getMessage() for record in caplog.records]
    assert any("retrying with normalized WAV" in message for message in messages)
