# Paidviewer Deploy Notes

## Role

`f5-tts-service` is the F5 provider runtime behind Paidviewer.

It is used in two contexts:

- cloud mode through `tts-gateway`
- self-host mode behind `tts_worker_agent`

## Required checks

- `GET /health/live`
- `GET /health/ready`
- `POST /v1/synthesize`
- one voice/admin compatibility request under `/api/tts/*`

## State boundary

This service may keep only F5-local operational state:

- voice catalog
- enabled voice pool
- F5-local limits/usage

User-facing routing/settings remain owned by `bot_service`.

## Upstream discipline

- keep `vendor/F5-TTS` aligned with `.upstream-pin`
- do not release from an unexplained dirty vendor state
- avoid `latest` tags in deploy examples
