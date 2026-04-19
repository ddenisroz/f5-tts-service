# Paidviewer Deploy Notes

Этот файл нужен тому, кто отдельно сопровождает `f5-tts-service`.

Если ты запускаешь весь проект целиком, начни с `paidviewer_tools/docs/QUICKSTART.md` в основном репозитории.

## Что это за сервис

`f5-tts-service` — это F5 runtime для Paidviewer.

Он используется в двух случаях:

- в `cloud` режиме за `tts-gateway`
- в `self_host` режиме за `tts_worker_agent`

## Что обязательно должно работать

- `GET /health/live`
- `GET /health/ready`
- `POST /v1/synthesize`
- хотя бы один совместимый voice/admin запрос под `/api/tts/*`

## Что этот сервис хранит

Только F5-локальное состояние:

- voice catalog
- enabled voice pool
- локальные лимиты и usage

Пользовательские настройки, маршрутизация и продуктовая логика остаются в `bot_service`.

## Что важно перед релизом

- `vendor/F5-TTS` должен совпадать с `.upstream-pin`
- нельзя выпускаться из необъяснённого dirty vendor state
- в deploy-примерах нельзя использовать `latest`
