# f5-tts-service

Provider-level F5 TTS engine service for Phase 1 architecture:

- base: `SWivid/F5-TTS` (vendor-pinned in `vendor/F5-TTS`)
- RU model weights: `Misha24-10/F5-TTS_RUSSIAN`
- RU preprocessing pipeline:
  - yo-fication
  - number/date/time/money normalization
  - accent dictionary
- internal provider API:
  - `POST /v1/synthesize`
  - `GET /health/live`
  - `GET /health/ready`
- compatibility voice/admin APIs used by current bot flows:
  - `/api/tts/*`
  - `/api/admin/*`

## Run

```bash
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8011
```

## Notes

- `F5_TTS_ENGINE_MODE=mock` is default for bootstrapping.
- Switch to real engine integration by setting `F5_TTS_ENGINE_MODE=real` and providing upstream deps.
- Audio files are served under `/api/tts/audio/{filename}`.

## Upstream Update

```powershell
./scripts/pin_upstream.ps1
```

This refreshes `vendor/F5-TTS` and rewrites `.upstream-pin` with the pinned commit.
