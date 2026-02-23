import logging
import time
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple
from sqlalchemy.orm import Session
from sqlalchemy import func, and_
from database import User, UserTTSUsage
logger = logging.getLogger(__name__)

class TTSLimitsService:
    """
    Сервис для управления ограничениями TTS и логирования использования
    """

    def __init__(self):
        self.global_max_text_length = 200
        self.global_daily_limit = 100
        self.global_gpu_time_limit = 300.0
        self.global_priority_level = 2
        import os
        self.global_max_text_length = int(os.getenv('TTS_MAX_TEXT_LENGTH', '200'))
        self.global_daily_limit = int(os.getenv('TTS_DAILY_LIMIT', '100'))
        self.global_gpu_time_limit = float(os.getenv('TTS_GPU_TIME_LIMIT', '300.0'))

    def get_user_limits(self, user_id: int, db: Session) -> Dict[str, Any]:
        """Получить лимиты пользователя"""
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return {'max_text_length': self.global_max_text_length, 'daily_limit': self.global_daily_limit, 'gpu_time_limit': self.global_gpu_time_limit, 'priority_level': self.global_priority_level, 'tts_enabled': True}
            return {'max_text_length': user.tts_max_text_length or self.global_max_text_length, 'daily_limit': user.tts_daily_limit or self.global_daily_limit, 'gpu_time_limit': user.tts_gpu_time_limit or self.global_gpu_time_limit, 'priority_level': user.tts_priority_level or self.global_priority_level, 'tts_enabled': user.tts_enabled if user.tts_enabled is not None else True}
        except Exception:
            logger.exception('Error getting user limits for user {user_id}')
            return {'max_text_length': self.global_max_text_length, 'daily_limit': self.global_daily_limit, 'gpu_time_limit': self.global_gpu_time_limit, 'priority_level': self.global_priority_level, 'tts_enabled': True}

    def update_user_limits(self, user_id: int, limits: Dict[str, Any], db: Session) -> bool:
        """Обновить лимиты пользователя"""
        try:
            user = db.query(User).filter(User.id == user_id).first()
            if not user:
                return False
            if 'max_text_length' in limits:
                user.tts_max_text_length = max(10, min(1000, limits['max_text_length']))
            if 'daily_limit' in limits:
                user.tts_daily_limit = max(1, min(1000, limits['daily_limit']))
            if 'gpu_time_limit' in limits:
                user.tts_gpu_time_limit = max(10.0, min(3600.0, limits['gpu_time_limit']))
            if 'priority_level' in limits:
                user.tts_priority_level = max(1, min(4, limits['priority_level']))
            if 'tts_enabled' in limits:
                user.tts_enabled = bool(limits['tts_enabled'])
            db.commit()
            logger.info(f'Updated TTS limits for user {user_id}: {limits}')
            return True
        except Exception:
            logger.exception('Error updating user limits for user {user_id}')
            db.rollback()
            return False

    def validate_request(self, user_id: int, text: str, db: Session) -> Tuple[bool, str, Dict[str, Any]]:
        """Проверить, можно ли выполнить запрос"""
        try:
            limits = self.get_user_limits(user_id, db)
            if not limits['tts_enabled']:
                return (False, 'TTS is disabled for this user', limits)
            if len(text) > limits['max_text_length']:
                return (False, f"Text too long. Maximum {limits['max_text_length']} characters, got {len(text)}", limits)
            today = datetime.now().date()
            usage = self.get_daily_usage(user_id, today, db)
            if usage['requests_count'] >= limits['daily_limit']:
                return (False, f"Daily request limit exceeded. Limit: {limits['daily_limit']}, used: {usage['requests_count']}", limits)
            if usage['gpu_time_seconds'] >= limits['gpu_time_limit']:
                return (False, f"Daily GPU time limit exceeded. Limit: {limits['gpu_time_limit']}s, used: {usage['gpu_time_seconds']}s", limits)
            return (True, 'Request allowed', limits)
        except Exception:
            logger.exception('Error validating request for user {user_id}')
            return (False, 'Validation error', {})

    def get_daily_usage(self, user_id: int, date: datetime.date, db: Session) -> Dict[str, Any]:
        """Получить использование за день"""
        try:
            start_of_day = datetime.combine(date, datetime.min.time())
            end_of_day = datetime.combine(date, datetime.max.time())
            usage = db.query(UserTTSUsage).filter(and_(UserTTSUsage.user_id == user_id, UserTTSUsage.date >= start_of_day, UserTTSUsage.date <= end_of_day)).first()
            if not usage:
                return {'requests_count': 0, 'gpu_time_seconds': 0.0, 'cpu_time_seconds': 0.0, 'total_characters': 0, 'successful_requests': 0, 'failed_requests': 0, 'gpu_requests': 0, 'cpu_requests': 0, 'critical_requests': 0, 'high_requests': 0, 'normal_requests': 0, 'low_requests': 0}
            return {'requests_count': usage.requests_count, 'gpu_time_seconds': usage.gpu_time_seconds, 'cpu_time_seconds': usage.cpu_time_seconds, 'total_characters': usage.total_characters, 'successful_requests': usage.successful_requests, 'failed_requests': usage.failed_requests, 'gpu_requests': usage.gpu_requests, 'cpu_requests': usage.cpu_requests, 'critical_requests': usage.critical_requests, 'high_requests': usage.high_requests, 'normal_requests': usage.normal_requests, 'low_requests': usage.low_requests}
        except Exception:
            logger.exception('Error getting daily usage for user {user_id}')
            return {}

    def log_request(self, user_id: int, text: str, processing_time: float, processing_type: str, priority: int, success: bool, db: Session) -> bool:
        """Логировать запрос пользователя"""
        try:
            today = datetime.now().date()
            start_of_day = datetime.combine(today, datetime.min.time())
            usage = db.query(UserTTSUsage).filter(and_(UserTTSUsage.user_id == user_id, UserTTSUsage.date >= start_of_day, UserTTSUsage.date < start_of_day + timedelta(days=1))).first()
            if not usage:
                usage = UserTTSUsage(user_id=user_id, date=start_of_day)
                db.add(usage)
            usage.requests_count += 1
            usage.total_characters += len(text)
            if success:
                usage.successful_requests += 1
            else:
                usage.failed_requests += 1
            if processing_type == 'gpu':
                usage.gpu_requests += 1
                usage.gpu_time_seconds += processing_time
            else:
                usage.cpu_requests += 1
                usage.cpu_time_seconds += processing_time
            if priority == 4:
                usage.critical_requests += 1
            elif priority == 3:
                usage.high_requests += 1
            elif priority == 2:
                usage.normal_requests += 1
            elif priority == 1:
                usage.low_requests += 1
            usage.updated_at = datetime.now()
            db.commit()
            logger.info(f'Logged TTS request for user {user_id}: {len(text)} chars, {processing_time:.2f}s {processing_type}, priority {priority}, success: {success}')
            return True
        except Exception:
            logger.exception('Error logging request for user {user_id}')
            db.rollback()
            return False

    def get_user_stats(self, user_id: int, days: int=7, db: Session=None) -> Dict[str, Any]:
        """Получить статистику пользователя за период"""
        try:
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)
            stats = db.query(func.sum(UserTTSUsage.requests_count).label('total_requests'), func.sum(UserTTSUsage.gpu_time_seconds).label('total_gpu_time'), func.sum(UserTTSUsage.cpu_time_seconds).label('total_cpu_time'), func.sum(UserTTSUsage.total_characters).label('total_characters'), func.sum(UserTTSUsage.successful_requests).label('successful_requests'), func.sum(UserTTSUsage.failed_requests).label('failed_requests'), func.sum(UserTTSUsage.gpu_requests).label('gpu_requests'), func.sum(UserTTSUsage.cpu_requests).label('cpu_requests')).filter(and_(UserTTSUsage.user_id == user_id, UserTTSUsage.date >= start_date, UserTTSUsage.date <= end_date)).first()
            if not stats or not stats.total_requests:
                return {'period_days': days, 'total_requests': 0, 'total_gpu_time': 0.0, 'total_cpu_time': 0.0, 'total_characters': 0, 'successful_requests': 0, 'failed_requests': 0, 'gpu_requests': 0, 'cpu_requests': 0, 'success_rate': 0.0, 'avg_processing_time': 0.0}
            success_rate = stats.successful_requests / stats.total_requests * 100 if stats.total_requests > 0 else 0
            avg_processing_time = (stats.total_gpu_time + stats.total_cpu_time) / stats.total_requests if stats.total_requests > 0 else 0
            return {'period_days': days, 'total_requests': stats.total_requests or 0, 'total_gpu_time': stats.total_gpu_time or 0.0, 'total_cpu_time': stats.total_cpu_time or 0.0, 'total_characters': stats.total_characters or 0, 'successful_requests': stats.successful_requests or 0, 'failed_requests': stats.failed_requests or 0, 'gpu_requests': stats.gpu_requests or 0, 'cpu_requests': stats.cpu_requests or 0, 'success_rate': round(success_rate, 2), 'avg_processing_time': round(avg_processing_time, 2)}
        except Exception:
            logger.exception('Error getting user stats for user {user_id}')
            return {}

    def get_global_stats(self, days: int=7, db: Session=None) -> Dict[str, Any]:
        """Получить глобальную статистику за период"""
        try:
            end_date = datetime.now().date()
            start_date = end_date - timedelta(days=days)
            stats = db.query(func.count(func.distinct(UserTTSUsage.user_id)).label('unique_users'), func.sum(UserTTSUsage.requests_count).label('total_requests'), func.sum(UserTTSUsage.gpu_time_seconds).label('total_gpu_time'), func.sum(UserTTSUsage.cpu_time_seconds).label('total_cpu_time'), func.sum(UserTTSUsage.total_characters).label('total_characters'), func.sum(UserTTSUsage.successful_requests).label('successful_requests'), func.sum(UserTTSUsage.failed_requests).label('failed_requests')).filter(and_(UserTTSUsage.date >= start_date, UserTTSUsage.date <= end_date)).first()
            if not stats or not stats.total_requests:
                return {'period_days': days, 'unique_users': 0, 'total_requests': 0, 'total_gpu_time': 0.0, 'total_cpu_time': 0.0, 'total_characters': 0, 'successful_requests': 0, 'failed_requests': 0, 'success_rate': 0.0, 'avg_requests_per_user': 0.0}
            success_rate = stats.successful_requests / stats.total_requests * 100 if stats.total_requests > 0 else 0
            avg_requests_per_user = stats.total_requests / stats.unique_users if stats.unique_users > 0 else 0
            return {'period_days': days, 'unique_users': stats.unique_users or 0, 'total_requests': stats.total_requests or 0, 'total_gpu_time': stats.total_gpu_time or 0.0, 'total_cpu_time': stats.total_cpu_time or 0.0, 'total_characters': stats.total_characters or 0, 'successful_requests': stats.successful_requests or 0, 'failed_requests': stats.failed_requests or 0, 'success_rate': round(success_rate, 2), 'avg_requests_per_user': round(avg_requests_per_user, 2)}
        except Exception:
            logger.exception('Error getting global stats')
            return {}
tts_limits_service = TTSLimitsService()
