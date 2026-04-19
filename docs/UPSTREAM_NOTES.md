# Upstream Notes

`vendor/F5-TTS` is pinned by `.upstream-pin` and must stay clean for release builds.

## Inference-only trainer import

The upstream package imports `f5_tts.model.trainer` from `f5_tts.model.__init__`.
That optional training stack is not required by this service and may fail in the
production inference image.

Do not patch the vendored submodule for this case. The service-owned workaround
lives in `app/engine/f5_engine.py`: on the first failed `f5_tts.api` import it
installs an inference-only `f5_tts.model.trainer` stub, clears the partially
loaded upstream modules, and retries the import. The behavior is covered by
`tests/test_f5_engine_logging.py`.
