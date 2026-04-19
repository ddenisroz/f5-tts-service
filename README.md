# f5-tts-service

F5 runtime-сервис для Paidviewer.

## Кому нужен этот репозиторий

Этот репозиторий нужен тому, кто поднимает или обслуживает F5-провайдер для Paidviewer.

Если ты обычный пользователь Paidviewer и не занимаешься инфраструктурой F5, этот репозиторий тебе обычно не нужен.

## Роль в системе

`f5-tts-service` — это provider-level сервис для F5.

Он используется для:

- `POST /v1/synthesize`
- F5 voice/admin compatibility API под `/api/tts/*` и `/api/admin/*`
- локального хранения F5 voice и service-level состояния

## Что важно понимать

- это не основной продуктовый backend
- `bot_service` остаётся источником истины для настроек пользователя и маршрутизации
- `f5-tts-service` хранит только F5-специфичное операционное состояние

## Upstream и pinning

- upstream лежит в `vendor/F5-TTS`
- зафиксированный commit указан в `.upstream-pin`
- для осознанного обновления upstream используй `scripts/pin_upstream.ps1`

## Быстрый запуск

Базовый runtime: Python `3.12`.

### Docker

```bash
docker build -t f5-tts-service:local .
docker run --rm -p 127.0.0.1:8011:8011 \
  -e F5_TTS_SERVICE_API_KEYS=change-me \
  -e F5_TTS_ENGINE_MODE=fake \
  -e F5_TTS_ENABLE_PREWARM=false \
  -e F5_TTS_TRANSCRIBER_ENABLED=false \
  -e F5_TTS_RUACCENT_ENABLED=false \
  f5-tts-service:local
```

Этот smoke-путь проверяет контейнер без загрузки модели. Для production включай `F5_TTS_ENGINE_MODE=real`, постоянное хранилище, БД и реальные веса.

### Локально без Docker

```bash
uv sync --python 3.12
uv run uvicorn app.main:app --host 0.0.0.0 --port 8011
```

## Health endpoints

- `GET /health/live`
- `GET /health/ready`

## Для деплоя

Короткий deploy/checklist лежит в `docs/PAIDVIEWER_DEPLOY.md`.
