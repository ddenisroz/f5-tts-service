# F5 TTS Service

FastAPI service for F5-based text-to-speech synthesis and voice management.

## What It Provides

- TTS synthesis API (`/api/tts/*`)
- voice management API (`/api/tts/voices/*`, `/api/admin/*`)
- health/readiness endpoints (`/health/live`, `/health/ready`)
- optional Redis worker mode for higher throughput

## Quick Start (Docker)

```bash
cp .env.production.example .env
docker compose -f deploy/docker-compose.simple.yml up -d --build
```

Set real values before first start:

- `SECRET_KEY`
- `POSTGRES_PASSWORD`
- `DATABASE_URL` (if not using compose-generated default)
- `INTERNAL_SERVICE_JWT_SECRET` (recommended)

Health check:

```bash
curl -f http://localhost:8001/health/live
curl -f http://localhost:8001/health/ready
```

## Quick Start (Local)

```bash
cp .env.example .env
pip install -r requirements.txt
python main.py
```

PowerShell:

```powershell
Copy-Item .env.example .env
pip install -r requirements.txt
python main.py
```

## Runtime Profiles

- `deploy/docker-compose.simple.yml`: API + PostgreSQL
- `deploy/docker-compose.advanced.yml`: API + PostgreSQL + Redis + workers

## Auth

Inter-service auth:

1. `Authorization: Bearer <service-jwt>` (recommended)
2. `X-Internal-Service-Key: <TTS_INTERNAL_API_KEY>` (compatibility)

## Documentation

- `docs/API_CONTRACT.md`
- `docs/DEPLOYMENT.md`
- `docs/RUNBOOK.md`
