# F5_tts/analysis_logging.py
"""
Analysis Logging for LLM Feature Verification

JSONL format optimized for LLM parsing during testing sessions.
Enable with environment variable: ANALYSIS_MODE=true
"""
import json
import logging
import logging.handlers
import os
import uuid
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

# Correlation ID for request tracing
_correlation_id: ContextVar[str] = ContextVar('correlation_id', default='')


def get_correlation_id() -> str:
    """Get current correlation ID or generate new one"""
    cid = _correlation_id.get()
    if not cid:
        cid = str(uuid.uuid4())[:8]
        _correlation_id.set(cid)
    return cid


def set_correlation_id(cid: str = None) -> str:
    """Set correlation ID for current context"""
    if cid is None:
        cid = str(uuid.uuid4())[:8]
    _correlation_id.set(cid)
    return cid


def clear_correlation_id():
    """Clear correlation ID"""
    _correlation_id.set('')


class JSONLFormatter(logging.Formatter):
    """Format log records as JSON Lines"""
    
    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": datetime.now().isoformat(),
            "level": record.levelname,
            "correlation_id": get_correlation_id(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        
        # Add extra fields from record
        if hasattr(record, 'feature'):
            log_data['feature'] = record.feature
        if hasattr(record, 'action'):
            log_data['action'] = record.action
        if hasattr(record, 'success'):
            log_data['success'] = record.success
        if hasattr(record, 'duration_ms'):
            log_data['duration_ms'] = record.duration_ms
        if hasattr(record, 'user_id'):
            log_data['user_id'] = record.user_id
        if hasattr(record, 'extra_data'):
            log_data['data'] = record.extra_data
        
        # Add exception info if present
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        return json.dumps(log_data, ensure_ascii=False, default=str)


class AnalysisLogger:
    """Logger for LLM analysis of feature correctness"""
    
    _instance: Optional['AnalysisLogger'] = None
    _initialized: bool = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self.enabled = os.getenv('ANALYSIS_MODE', '').lower() in ('true', '1', 'yes')
        self.logger = logging.getLogger('f5_tts.analysis')
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False  # Don't send to parent loggers
        
        if self.enabled:
            self._setup_handlers()
        
        self._initialized = True
    
    def _setup_handlers(self):
        """Setup file handler for analysis logs"""
        # Create analysis logs directory
        service_root = Path(__file__).resolve().parent
        log_dir = service_root / "logs" / "analysis"
        log_dir.mkdir(parents=True, exist_ok=True)
        
        log_file = log_dir / "f5_tts_analysis.jsonl"
        
        # Rotating file handler (50MB max, keep 5 files for ~6 hours of testing)
        handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=50 * 1024 * 1024,  # 50 MB
            backupCount=5,
            encoding='utf-8'
        )
        handler.setFormatter(JSONLFormatter())
        handler.setLevel(logging.DEBUG)
        
        self.logger.handlers.clear()
        self.logger.addHandler(handler)
        
        # Also log to console in debug format
        console = logging.StreamHandler()
        console.setLevel(logging.INFO)
        console.setFormatter(logging.Formatter(
            '[ANALYSIS] %(asctime)s - %(message)s'
        ))
        self.logger.addHandler(console)
        
        self.logger.info("Analysis logging initialized", extra={
            'feature': 'system',
            'action': 'init',
            'extra_data': {'log_file': str(log_file)}
        })
    
    def log(
        self,
        feature: str,
        action: str,
        message: str,
        success: bool = True,
        duration_ms: float = None,
        user_id: int = None,
        level: int = logging.INFO,
        **extra
    ):
        """Log a feature event for analysis"""
        if not self.enabled:
            return
        
        record_extra = {
            'feature': feature,
            'action': action,
            'success': success,
        }
        if duration_ms is not None:
            record_extra['duration_ms'] = round(duration_ms, 2)
        if user_id is not None:
            record_extra['user_id'] = user_id
        if extra:
            record_extra['extra_data'] = extra
        
        self.logger.log(level, message, extra=record_extra)


# Global instance
_analysis_logger: Optional[AnalysisLogger] = None


def get_analysis_logger() -> AnalysisLogger:
    """Get the global analysis logger instance"""
    global _analysis_logger
    if _analysis_logger is None:
        _analysis_logger = AnalysisLogger()
    return _analysis_logger


# ============ TTS-Specific Convenience Functions ============

def log_feature(
    feature: str,
    action: str,
    message: str,
    success: bool = True,
    duration_ms: float = None,
    user_id: int = None,
    **extra
):
    """Log a generic feature event"""
    get_analysis_logger().log(
        feature=feature,
        action=action,
        message=message,
        success=success,
        duration_ms=duration_ms,
        user_id=user_id,
        **extra
    )


def log_tts_generation(
    text: str,
    voice: str,
    success: bool = True,
    user_id: int = None,
    duration_ms: float = None,
    audio_duration_sec: float = None,
    audio_size_bytes: int = None,
    error: str = None
):
    """Log TTS generation event"""
    log_feature(
        feature='tts_generation',
        action='generate',
        message=f"TTS: {len(text)} chars -> {audio_duration_sec:.1f}s audio" if audio_duration_sec else f"TTS: {len(text)} chars",
        success=success,
        duration_ms=duration_ms,
        user_id=user_id,
        text_length=len(text),
        text_preview=text[:100] if len(text) > 100 else text,
        voice=voice,
        audio_duration_sec=audio_duration_sec,
        audio_size_bytes=audio_size_bytes,
        error=error
    )


def log_audio_conversion(
    input_format: str,
    output_format: str,
    success: bool = True,
    duration_ms: float = None,
    input_size: int = None,
    output_size: int = None,
    error: str = None
):
    """Log audio conversion event"""
    log_feature(
        feature='audio_conversion',
        action='convert',
        message=f"Convert {input_format} -> {output_format}",
        success=success,
        duration_ms=duration_ms,
        input_format=input_format,
        output_format=output_format,
        input_size=input_size,
        output_size=output_size,
        error=error
    )


def log_voice_selection(
    requested_voice: str,
    selected_voice: str,
    available_voices: list = None,
    user_id: int = None,
    success: bool = True
):
    """Log voice pool selection event"""
    log_feature(
        feature='voice_selection',
        action='select',
        message=f"Voice: {requested_voice} -> {selected_voice}",
        success=success,
        user_id=user_id,
        requested_voice=requested_voice,
        selected_voice=selected_voice,
        available_count=len(available_voices) if available_voices else 0
    )


def log_rate_limit(
    user_id: int,
    action: str,  # 'check', 'exceeded', 'reset'
    current_usage: int = None,
    limit: int = None,
    remaining: int = None,
    success: bool = True
):
    """Log rate limiting event"""
    log_feature(
        feature='rate_limit',
        action=action,
        message=f"Rate limit {action}: {current_usage}/{limit}" if current_usage and limit else f"Rate limit {action}",
        success=success,
        user_id=user_id,
        current_usage=current_usage,
        limit=limit,
        remaining=remaining
    )


def log_gpu_worker(
    action: str,  # 'queue', 'start', 'complete', 'error'
    worker_id: str = None,
    queue_size: int = None,
    gpu_memory_used: float = None,
    duration_ms: float = None,
    success: bool = True,
    error: str = None
):
    """Log GPU worker status"""
    log_feature(
        feature='gpu_worker',
        action=action,
        message=f"GPU worker {action}",
        success=success,
        duration_ms=duration_ms,
        worker_id=worker_id,
        queue_size=queue_size,
        gpu_memory_used_mb=gpu_memory_used,
        error=error
    )


def log_api_request(
    method: str,
    endpoint: str,
    status_code: int,
    duration_ms: float = None,
    user_id: int = None,
    request_size: int = None,
    response_size: int = None
):
    """Log API request"""
    success = 200 <= status_code < 400
    log_feature(
        feature='api_request',
        action=method.lower(),
        message=f"{method} {endpoint} -> {status_code}",
        success=success,
        duration_ms=duration_ms,
        user_id=user_id,
        endpoint=endpoint,
        status_code=status_code,
        request_size=request_size,
        response_size=response_size
    )


def log_error(
    feature: str,
    error: Exception,
    context: str = None,
    user_id: int = None,
    **extra
):
    """Log an error for analysis"""
    get_analysis_logger().log(
        feature=feature,
        action='error',
        message=f"Error in {feature}: {str(error)}",
        success=False,
        user_id=user_id,
        level=logging.ERROR,
        error_type=type(error).__name__,
        error_message=str(error),
        context=context,
        **extra
    )

