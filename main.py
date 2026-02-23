"""Entrypoint for the F5_tts service."""

import os
import sys
from pathlib import Path

import uvicorn

from analysis_logging import get_analysis_logger
from app_factory import create_app
from logging_config import LoggingConfig

SERVICE_NAME = "f5_tts"
SERVICE_ROOT = Path(__file__).resolve().parent
if str(SERVICE_ROOT) not in sys.path:
    sys.path.insert(0, str(SERVICE_ROOT))

logging_config = LoggingConfig(SERVICE_NAME)
app_log_level = os.getenv("LOG_LEVEL", "INFO")
logger = logging_config.setup_logging(app_log_level)

# Optional JSONL analysis logs used in diagnostics sessions.
analysis_logger = get_analysis_logger()


def main() -> None:
    """Start the FastAPI application with Uvicorn."""
    try:
        app = create_app()
        host = os.getenv("TTS_HOST", "0.0.0.0")
        port = int(os.getenv("TTS_PORT", "8001"))
        uvicorn_log_level = os.getenv("TTS_LOG_LEVEL", "info").lower()

        logger.info("[START] Starting F5_tts on %s:%s", host, port)
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level=uvicorn_log_level,
            access_log=True,
            use_colors=False,
            log_config=None,
        )
    except Exception:
        logger.exception("[ERROR] Failed to start F5_tts")
        raise


if __name__ == "__main__":
    main()
