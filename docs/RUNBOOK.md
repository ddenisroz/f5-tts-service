# Operations Runbook

## Startup Checklist

1. verify `.env` has no placeholder secrets
2. start `simple` or `advanced` profile
3. check `200` for `/health/live` and `/health/ready`
4. run one synthesis request through your client integration

## Smoke Commands

```bash
curl -sS http://localhost:8001/health/live
curl -sS http://localhost:8001/health/ready
curl -sS http://localhost:8001/api/tts/voices
```

## Incident Guide

`/health/ready` returns `503`:

- verify PostgreSQL and `DATABASE_URL`
- check model init logs
- check background tasks status

internal `401` between services:

- verify JWT secret/issuer/audience/subject alignment
- verify `TTS_INTERNAL_API_KEY` only if fallback is enabled

latency or queue growth (advanced):

- verify Redis health
- verify worker count and worker logs
- verify GPU saturation and task timeout metrics

## Routine Maintenance

- rotate internal auth secrets
- prune old logs and temporary audio artifacts
- validate backups and restore flow
- monitor p95/p99 latency and synthesis error rate
