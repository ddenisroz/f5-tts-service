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
  - includes enabled-voice pool selection and TTS limits/stats endpoints
  - includes voice upload conversion to WAV + automatic transcription
  - includes `/api/tts/enable|disable|status` compatibility controls

## Run

```bash
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8011
```

## Notes

- `F5_TTS_ENGINE_MODE=real` is the default. Service starts only with real engine integration.
- All relative paths are resolved from `F5_TTS_BASE_DIR` (default `.`).
- Voice uploads require `ffmpeg` (preferred) or `pydub` backend, and store WAV in `F5_TTS_VOICES_DIR` (default `data/voices`).
- Upload security/quality controls:
  - `F5_TTS_VOICE_UPLOAD_MAX_BYTES`
  - `F5_TTS_VOICE_UPLOAD_MIN_DURATION_SEC`
  - `F5_TTS_VOICE_UPLOAD_MAX_DURATION_SEC`
- Automatic reference transcription uses `faster-whisper` when `F5_TTS_TRANSCRIBER_ENABLED=true`.
- Audio files are served under `/api/tts/audio/{filename}`.
- Auth is strict API key only (`F5_TTS_SERVICE_API_KEYS`), no JWT/no-anon mode.
- Text input is guarded by `F5_TTS_MAX_INPUT_TEXT_LENGTH`.
- Voice catalog storage:
  - default fallback: file store (`data/voices/state.json`)
  - PostgreSQL mode: set `F5_TTS_DATABASE_URL=postgresql://user:pass@host:5432/dbname`
  - tables are auto-created at startup (`voices`, `user_voice_enabled`)
- TTS limits/usage storage:
  - default fallback: file store (`data/limits/state.json`)
  - PostgreSQL mode: same `F5_TTS_DATABASE_URL`
  - tables are auto-created at startup (`tts_user_limits`, `tts_usage_daily`)

## State Boundaries

- `bot_service` remains source of truth for:
  - provider choice (`f5|qwen|gcloud`)
  - per-user UI settings and routing decisions
- `f5-tts-service` stores only F5-local operational state:
  - voice catalog and per-user enabled voice pool
  - F5 limits and usage counters

## PostgreSQL Example

```bash
export F5_TTS_DATABASE_URL="postgresql://f5tts:secret@localhost:5432/f5tts"
export F5_TTS_DATABASE_ECHO=false
```

## Database Migrations

```bash
uv run alembic upgrade head
```

Alembic reads `F5_TTS_DATABASE_URL` from environment/.env.

## State Migration (File -> PostgreSQL)

```bash
uv run python scripts/migrate_file_state_to_postgres.py --mode replace
```

Modes:

- `replace` - clear target DB tables before importing file state.
- `merge` - upsert file state without truncating target DB tables.

## Upstream Update

```powershell
./scripts/pin_upstream.ps1
```

This refreshes `vendor/F5-TTS` and rewrites `.upstream-pin` with the pinned commit.
