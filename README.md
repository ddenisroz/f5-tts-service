# f5-tts-service

Provider-level F5 runtime for Paidviewer.

## Production role

`f5-tts-service` is the F5 engine service used by Paidviewer for:

- `POST /v1/synthesize`
- F5 voice/admin compatibility APIs under `/api/tts/*` and `/api/admin/*`
- local F5 voice and limits storage

## Upstream and pinning

- upstream is vendored in `vendor/F5-TTS`
- pinned commit is recorded in `.upstream-pin`
- use `scripts/pin_upstream.ps1` when intentionally refreshing upstream

## Run

```bash
uv sync
uv run uvicorn app.main:app --host 0.0.0.0 --port 8011
```

## Required runtime notes

- this repo is the F5 provider service, not the product orchestrator
- `bot_service` remains the source of truth for user settings and routing policy
- `f5-tts-service` stores only F5-local operational state

## Health

- `GET /health/live`
- `GET /health/ready`

## Paidviewer deploy notes

See `docs/PAIDVIEWER_DEPLOY.md` for the short production checklist.
