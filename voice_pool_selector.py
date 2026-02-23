# F5_tts/voice_pool_selector.py
"""Утилиты для выбора голоса из пула включенных голосов пользователя"""
import logging
import random
from sqlalchemy.orm import Session
from typing import Optional, List

from database import Voice as VoiceModel, UserVoiceEnabled

logger = logging.getLogger(__name__)


def get_enabled_voices_for_user(user_id: int, db: Session) -> List[VoiceModel]:
    """
    Получить список включенных голосов для пользователя.
    Если нет записей в UserVoiceEnabled, возвращает все активные голоса.
    """
    try:
        # Проверяем есть ли записи о включенных голосах
        enabled_records = db.query(UserVoiceEnabled).filter(
            UserVoiceEnabled.user_id == user_id,
            UserVoiceEnabled.is_enabled.is_(True)
        ).all()
        
        if enabled_records:
            # Есть настройки - возвращаем только включенные голоса
            voice_ids = [record.voice_id for record in enabled_records]
            voices = db.query(VoiceModel).filter(
                VoiceModel.id.in_(voice_ids),
                VoiceModel.is_active.is_(True)
            ).all()
            logger.info(f"Found {len(voices)} enabled voices for user {user_id}")
            return voices
        else:
            # Нет настроек - возвращаем все активные голоса (дефолтное поведение)
            voices = db.query(VoiceModel).filter(
                VoiceModel.is_active.is_(True)
            ).all()
            logger.info(f"No voice preferences found for user {user_id}, returning all {len(voices)} active voices")
            return voices
            
    except Exception:
        logger.exception("Error getting enabled voices for user {user_id}")
        # В случае ошибки возвращаем все активные голоса
        return db.query(VoiceModel).filter(VoiceModel.is_active.is_(True)).all()


def select_random_voice_from_pool(user_id: int, db: Session) -> Optional[str]:
    """
    Выбрать случайный голос из пула включенных голосов пользователя.
    Возвращает имя голоса или None если нет доступных голосов.
    """
    try:
        enabled_voices = get_enabled_voices_for_user(user_id, db)
        
        if not enabled_voices:
            logger.warning(f"No enabled voices found for user {user_id}")
            return None
        
        # Выбираем случайный голос из пула
        selected_voice = random.choice(enabled_voices)
        logger.info(f"Selected voice '{selected_voice.name}' for user {user_id} from pool of {len(enabled_voices)} voices")
        
        return selected_voice.name
        
    except Exception:
        logger.exception("Error selecting random voice for user {user_id}")
        return None


def get_voice_or_random_from_pool(
    user_id: int, 
    voice_name: Optional[str], 
    db: Session
) -> Optional[str]:
    """
    Получить голос для синтеза:
    - Если voice_name указан и включен для пользователя - использовать его
    - Если voice_name не указан - выбрать случайный из пула
    - Если voice_name указан но не включен - выбрать случайный из пула
    """
    try:
        # Если голос не указан - выбираем случайный из пула
        if not voice_name or voice_name == 'random':
            return select_random_voice_from_pool(user_id, db)
        
        # Проверяем включен ли указанный голос
        voice = db.query(VoiceModel).filter(
            VoiceModel.name == voice_name,
            VoiceModel.is_active.is_(True)
        ).first()
        
        if not voice:
            logger.warning(f"Voice '{voice_name}' not found or inactive for user {user_id}, selecting random")
            return select_random_voice_from_pool(user_id, db)
        
        # Проверяем есть ли настройки включенных голосов
        enabled_record = db.query(UserVoiceEnabled).filter(
            UserVoiceEnabled.user_id == user_id,
            UserVoiceEnabled.voice_id == voice.id
        ).first()
        
        # Если есть запись и голос отключен - выбираем случайный
        if enabled_record and not enabled_record.is_enabled:
            logger.warning(f"Voice '{voice_name}' is disabled for user {user_id}, selecting random")
            return select_random_voice_from_pool(user_id, db)
        
        # Если записи нет - значит все голоса включены по умолчанию
        logger.info(f"Using requested voice '{voice_name}' for user {user_id}")
        return voice_name
        
    except Exception:
        logger.exception("Error in get_voice_or_random_from_pool for user {user_id}")
        # В случае ошибки пытаемся вернуть запрошенный голос или дефолтный
        return voice_name if voice_name else 'female_1'




