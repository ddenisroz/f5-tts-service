from __future__ import annotations

import json
import logging
import re
from types import MethodType
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

ACCENT_MARK = "\u0301"
WORD_RE = re.compile(rf"\b[А-Яа-яЁёA-Za-z{ACCENT_MARK}-]+\b", re.UNICODE)
DEFAULT_ACCENT_OVERRIDES_PATH = Path(__file__).with_name("accent_overrides.json")


class Accentor:
    def __init__(self, dictionary_path: Path, *, model_size: str = "turbo", enabled: bool = True) -> None:
        self.dictionary: dict[str, str] = {}
        self.model_size = model_size
        self.enabled = enabled
        self.accentizer: Any | None = None
        self._load_dictionary(DEFAULT_ACCENT_OVERRIDES_PATH)
        if dictionary_path.resolve() != DEFAULT_ACCENT_OVERRIDES_PATH.resolve():
            self._load_dictionary(dictionary_path)
        if self.enabled:
            self._load_ruaccent()
        else:
            logger.info("RUAccent disabled by configuration; using accent override dictionary only")

    def apply(self, text: str) -> str:
        if not text or not text.strip():
            return text
        updated = text

        if self.accentizer is not None:
            try:
                if hasattr(self.accentizer, "process_all"):
                    updated = self.accentizer.process_all(updated)
                elif hasattr(self.accentizer, "process"):
                    updated = self.accentizer.process(updated)
            except Exception:
                logger.warning("RUAccent failed while applying accents; keeping fallback behavior", exc_info=True)

        def _replace(match: re.Match[str]) -> str:
            original = match.group(0)
            replacement = self.dictionary.get(self._strip_accents(original.lower()))
            if not replacement:
                return original
            if original.isupper():
                return replacement.upper()
            if original[:1].isupper():
                return replacement[:1].upper() + replacement[1:]
            return replacement

        return WORD_RE.sub(_replace, updated)

    def _load_dictionary(self, dictionary_path: Path) -> None:
        if not dictionary_path.exists():
            return
        try:
            payload = json.loads(dictionary_path.read_text(encoding="utf-8"))
            self.dictionary = {str(key).lower(): str(value) for key, value in payload.items()}
            logger.info("Loaded accent overrides from %s entries=%s", dictionary_path, len(self.dictionary))
        except Exception:
            logger.exception("Failed to load accent overrides from %s", dictionary_path)
            self.dictionary = {}

    def _load_ruaccent(self) -> None:
        try:
            accentizer = self._build_ruaccent()
        except Exception as error:
            logger.warning("RUAccent is unavailable; using accent override dictionary only: %s", error)
            self.accentizer = None
            return
        try:
            if hasattr(accentizer, "load"):
                accentizer.load(omograph_model_size=self.model_size, use_dictionary=True)
            self._patch_ruaccent_onnx_inputs(accentizer)
            self.accentizer = accentizer
            logger.info("RUAccent loaded successfully model_size=%s", self.model_size)
        except Exception as error:
            logger.warning("RUAccent failed to load; using accent override dictionary only: %s", error)
            self.accentizer = None

    @staticmethod
    def _patch_ruaccent_onnx_inputs(accentizer: Any) -> None:
        """Adapt RUAccent accent ONNX feed to models that require token_type_ids."""
        accent_model = getattr(accentizer, "accent_model", None)
        session = getattr(accent_model, "session", None)
        tokenizer = getattr(accent_model, "tokenizer", None)
        if accent_model is None or session is None or tokenizer is None:
            return
        if getattr(accent_model, "_paidviewer_token_type_ids_patch", False):
            return

        input_names = {input_info.name for input_info in session.get_inputs()}
        if "token_type_ids" not in input_names:
            return

        try:
            from ruaccent import accent_model as ruaccent_accent_model
        except Exception as error:
            logger.warning("RUAccent token_type_ids patch skipped: %s", error)
            return

        np = ruaccent_accent_model.np
        softmax = ruaccent_accent_model.softmax

        def patched_put_accent(model_self: Any, word: str) -> str:
            lower_word = word.lower()
            inputs = model_self.tokenizer(lower_word, return_tensors="np")
            inputs = {key: value.astype(np.int64) for key, value in inputs.items()}
            input_ids = inputs.get("input_ids")
            if "token_type_ids" in input_names and "token_type_ids" not in inputs and input_ids is not None:
                inputs["token_type_ids"] = np.zeros_like(input_ids, dtype=np.int64)
            filtered_inputs = {key: value for key, value in inputs.items() if key in input_names}

            outputs = model_self.session.run(None, filtered_inputs)
            output_names = {output_key.name: idx for idx, output_key in enumerate(model_self.session.get_outputs())}
            logits = outputs[output_names["logits"]]
            probabilities = softmax(logits)
            scores = np.max(probabilities, axis=-1)[0]
            labels = np.argmax(logits, axis=-1)[0]
            pred_with_scores = [
                {"label": model_self.id2label[str(label)], "score": float(score)}
                for label, score in zip(labels, scores)
            ]

            return model_self.render_stress(word, pred_with_scores)

        accent_model.put_accent = MethodType(patched_put_accent, accent_model)
        accent_model._paidviewer_token_type_ids_patch = True
        logger.info("RUAccent ONNX token_type_ids compatibility patch enabled")

    @staticmethod
    def _build_ruaccent():
        from ruaccent import RUAccent

        return RUAccent()

    @staticmethod
    def _strip_accents(text: str) -> str:
        return text.replace(ACCENT_MARK, "")

