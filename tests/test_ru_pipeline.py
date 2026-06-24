from __future__ import annotations

import json

from app.ru_pipeline import RuPipeline
from app.ru_pipeline.accentor import Accentor


class _NoopRuAccent:
    def load(self, **kwargs) -> None:
        return

    def process_all(self, text: str) -> str:
        return text


def _build_pipeline(tmp_path, monkeypatch) -> RuPipeline:
    monkeypatch.setattr(Accentor, "_build_ruaccent", staticmethod(lambda: _NoopRuAccent()))
    yo_path = tmp_path / "yo.json"
    yo_path.write_text(
        json.dumps(
            {
                "елка": "ёлка",
                "осел": "осёл",
                "еще": "ещё",
                "все": "всё",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    accents_path = tmp_path / "accents.json"
    accents_path.write_text("{}", encoding="utf-8")
    return RuPipeline.create(yo_path, accents_path)


def test_ru_pipeline_restores_legacy_normalization(workspace_tmp_path, monkeypatch) -> None:
    pipeline = _build_pipeline(workspace_tmp_path, monkeypatch)

    output = pipeline.process("еще не все, елка и осел. Сегодня 12.03.2026 в 14:05, цена 250 руб и 7")

    assert "ещё" in output
    assert "всё" in output
    assert "ёлка" in output
    assert "осёл" in output
    assert "двенадцатое марта две тысячи двадцать шесть года" in output
    assert "четырнадцать часов пять минут" in output
    assert "двести пятьдесят рублей" in output
    assert "семь" in output
    assert output.endswith(".")


def test_ru_pipeline_keeps_english_text_and_adds_final_punctuation(workspace_tmp_path, monkeypatch) -> None:
    pipeline = _build_pipeline(workspace_tmp_path, monkeypatch)

    output = pipeline.process("hello world")

    assert output == "hello world."


def test_ru_pipeline_applies_to_mixed_cyrillic_url_and_emote(workspace_tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(Accentor, "_build_ruaccent", staticmethod(lambda: _NoopRuAccent()))
    yo_path = workspace_tmp_path / "yo-mixed.json"
    yo_path.write_text(
        json.dumps({"\u0435\u0449\u0435": "\u0435\u0449\u0451"}, ensure_ascii=False),
        encoding="utf-8",
    )
    accents_path = workspace_tmp_path / "accents-mixed.json"
    accents_path.write_text("{}", encoding="utf-8")
    pipeline = RuPipeline.create(yo_path, accents_path)

    output = pipeline.process("HYPE https://example.test/watch @viewer \u0435\u0449\u0435")

    assert "\u0435\u0449\u0451" in output
    assert "HYPE" in output
    assert "https://example.test/watch" in output
    assert output.endswith(".")


def test_ru_pipeline_drops_empty_or_symbol_only_input(workspace_tmp_path, monkeypatch) -> None:
    pipeline = _build_pipeline(workspace_tmp_path, monkeypatch)

    assert pipeline.process("   ") == ""
    assert pipeline.process("!!!???") == ""
