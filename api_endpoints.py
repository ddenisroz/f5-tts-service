from fastapi import APIRouter
from routers import system, synthesis, media, users

# Создаем основной роутер
tts_api = APIRouter()

# Подключаем роутеры
tts_api.include_router(system.router)
tts_api.include_router(synthesis.router)
tts_api.include_router(media.router)
tts_api.include_router(users.router)

# No re-exports needed as app_factory imports tts_api from here.

