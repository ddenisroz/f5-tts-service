from __future__ import annotations

import json

import numpy as np

from app.ru_pipeline.accentor import Accentor
from app.ru_pipeline.yoficator import Yoficator


class _FakeRuAccent:
    def load(self, **kwargs) -> None:
        self.load_kwargs = kwargs

    def process_all(self, text: str) -> str:
        return text.replace("привет", "приве́т").replace("красивее", "красиве́е")


class _BrokenRuAccent:
    def load(self, **kwargs) -> None:
        return

    def process_all(self, text: str) -> str:
        raise RuntimeError("boom")


class _FakeOnnxInput:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeOnnxSession:
    def __init__(self) -> None:
        self.input_feed = None

    def get_inputs(self):
        return [_FakeOnnxInput("input_ids"), _FakeOnnxInput("attention_mask"), _FakeOnnxInput("token_type_ids")]

    def get_outputs(self):
        return [_FakeOnnxInput("logits")]

    def run(self, _output_names, input_feed):
        self.input_feed = input_feed
        return [np.array([[[0.1, 0.9], [0.9, 0.1]]], dtype=np.float32)]


class _FakeTokenTypeAccentModel:
    def __init__(self) -> None:
        self.session = _FakeOnnxSession()
        self.id2label = {"0": "NO", "1": "STRESS"}

    def tokenizer(self, _word: str, return_tensors: str):
        assert return_tensors == "np"
        return {
            "input_ids": np.array([[1, 2]], dtype=np.int64),
            "attention_mask": np.array([[1, 1]], dtype=np.int64),
        }

    def render_stress(self, word: str, _pred):
        return word


class _FakeTokenTypeRuAccent:
    def __init__(self) -> None:
        self.accent_model = _FakeTokenTypeAccentModel()


def test_yoficator_supports_dat_dictionary(workspace_tmp_path) -> None:
    dictionary_path = workspace_tmp_path / "custom.dat"
    dictionary_path.write_text("еще|ещё\nосел|осёл\n", encoding="utf-8")

    yoficator = Yoficator(dictionary_path)

    assert yoficator.apply("еще осел") == "ещё осёл"


def test_yoficator_supports_json_overrides(workspace_tmp_path) -> None:
    dictionary_path = workspace_tmp_path / "custom.json"
    dictionary_path.write_text(json.dumps({"елка": "ёлка"}, ensure_ascii=False), encoding="utf-8")

    yoficator = Yoficator(dictionary_path)

    assert yoficator.apply("елка") == "ёлка"


def test_yoficator_uses_heuristics_when_dictionary_misses_word(workspace_tmp_path) -> None:
    dictionary_path = workspace_tmp_path / "empty.json"
    dictionary_path.write_text("{}", encoding="utf-8")

    yoficator = Yoficator(dictionary_path)

    assert yoficator.apply("завел") == "завёл"


def test_accentor_prefers_dictionary_overrides_after_ruaccent(workspace_tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(Accentor, "_build_ruaccent", staticmethod(lambda: _FakeRuAccent()))
    dictionary_path = workspace_tmp_path / "accents.json"
    dictionary_path.write_text(json.dumps({"красивее": "краси́вее"}, ensure_ascii=False), encoding="utf-8")

    accentor = Accentor(dictionary_path)

    assert accentor.apply("привет красивее") == "приве́т краси́вее"


def test_accentor_degrades_cleanly_when_ruaccent_is_unavailable(workspace_tmp_path, monkeypatch) -> None:
    def _raise_import_error():
        raise ImportError("missing")

    monkeypatch.setattr(Accentor, "_build_ruaccent", staticmethod(_raise_import_error))
    dictionary_path = workspace_tmp_path / "accents.json"
    dictionary_path.write_text(json.dumps({"привет": "приве́т"}, ensure_ascii=False), encoding="utf-8")

    accentor = Accentor(dictionary_path)

    assert accentor.apply("привет мир") == "приве́т мир"


def test_accentor_degrades_cleanly_when_ruaccent_apply_fails(workspace_tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(Accentor, "_build_ruaccent", staticmethod(lambda: _BrokenRuAccent()))
    dictionary_path = workspace_tmp_path / "accents.json"
    dictionary_path.write_text(json.dumps({"привет": "приве́т"}, ensure_ascii=False), encoding="utf-8")

    accentor = Accentor(dictionary_path)

    assert accentor.apply("привет мир") == "приве́т мир"


def test_accentor_adds_token_type_ids_for_ruaccent_onnx_model() -> None:
    accentizer = _FakeTokenTypeRuAccent()

    Accentor._patch_ruaccent_onnx_inputs(accentizer)
    assert accentizer.accent_model.put_accent("слово") == "слово"

    input_feed = accentizer.accent_model.session.input_feed
    assert input_feed is not None
    assert set(input_feed) == {"input_ids", "attention_mask", "token_type_ids"}
    assert np.array_equal(input_feed["token_type_ids"], np.zeros_like(input_feed["input_ids"]))
