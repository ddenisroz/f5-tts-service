# Deployment

## Prerequisites

- Docker + Docker Compose v2
- `.env` created from:
  - `.env.production.example` for production
  - `.env.example` for local/dev
- NVIDIA runtime only if GPU mode is required

## Required Environment

- `SECRET_KEY`
- `DATABASE_URL`

Recommended for service-to-service auth:

- `INTERNAL_SERVICE_JWT_SECRET`
- `INTERNAL_SERVICE_JWT_ISSUER`
- `INTERNAL_SERVICE_JWT_AUDIENCE`
- `INTERNAL_SERVICE_JWT_ALLOWED_SUBJECTS`

Fallback compatibility key:

- `TTS_INTERNAL_API_KEY`

Advanced profile only:

- `REDIS_URL`
- `GPU_REDIS_URL`

## Start Profiles

From repository root:

Simple:

```bash
docker compose -f deploy/docker-compose.simple.yml up -d --build
```

Advanced:

```bash
docker compose -f deploy/docker-compose.advanced.yml up -d --build
```

## Validate

```bash
curl -f http://localhost:8001/health/live
curl -f http://localhost:8001/health/ready
```

## Security Baseline

- do not expose PostgreSQL/Redis publicly
- keep secrets in environment or secret manager
- use service JWT as primary internal auth
- keep API key fallback only while migrating clients
