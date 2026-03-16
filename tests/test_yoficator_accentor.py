from __future__ import annotations

import json

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
