# API Contract

## Base URL

- Default local: `http://localhost:8001`

## Authentication

Supported inter-service auth methods:

1. `Authorization: Bearer <service-jwt>` (recommended)
2. `X-Internal-Service-Key: <TTS_INTERNAL_API_KEY>` (compatibility fallback)

Expected service JWT claims:

- `type=service`
- `iss=<INTERNAL_SERVICE_JWT_ISSUER>`
- `aud=<INTERNAL_SERVICE_JWT_AUDIENCE>`
- `sub` in `INTERNAL_SERVICE_JWT_ALLOWED_SUBJECTS`

## Health

- `GET /health/live`
- `GET /health/ready`
- `GET /health` (legacy alias)
- `GET /api/health` (legacy alias)
- `GET /detailed`
- `GET /metrics`

## Core Endpoints

Synthesis:

- `POST /api/tts/synthesize-channel`
- `GET /api/tts/task/{task_id}`

Voices:

- `GET /api/tts/voices`
- `GET /api/tts/voices/global`
- `GET /api/tts/voices/{voice_id}`
- `GET /api/tts/user/voices/{user_id}`
- `POST /api/tts/user/voices/upload`
- `DELETE /api/tts/user/voices/{voice_id}`
- `PUT /api/tts/user/voices/{voice_id}/rename`
- `POST /api/tts/user/voices/{voice_id}/retranscribe`
- `PUT /api/tts/user/voices/{voice_id}/settings`

User enabled voices:

- `GET /api/tts/user/voices/enabled/{user_id}`
- `POST /api/tts/user/voices/enabled/{user_id}`
- `PUT /api/tts/user/voices/enabled/{user_id}/{voice_id}`

Admin:

- `GET /api/admin/voices`
- `POST /api/admin/voices/upload`
- `PUT /api/admin/voices/{voice_id}/settings`
- `DELETE /api/admin/voices/{voice_id}`
- `PUT /api/admin/voices/{voice_id}/rename`
- `POST /api/admin/voices/{voice_id}/retranscribe`
- `POST /api/admin/voices/{voice_id}/toggle`
- `GET /api/admin/stats`
- `GET /api/admin/system/status`
- `POST /api/admin/system/restart`

## Deprecation Policy

- Legacy endpoints return standard deprecation headers during grace period.
- Breaking changes require one release of warning headers before removal.
