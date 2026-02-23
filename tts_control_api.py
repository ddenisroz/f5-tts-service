"""TTS Control API endpoints."""

from typing import Any, Dict
import logging

from fastapi import APIRouter, Depends, HTTPException

from auth import get_current_user_or_internal

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["tts-control"])

# In-memory state store. Replace with DB-backed state for multi-instance deployments.
_tts_states: Dict[int, Dict[str, bool]] = {}


def _actor_user_id(current_user: Dict[str, Any]) -> int:
    user_id = current_user.get("user_id", current_user.get("id"))
    if not isinstance(user_id, int):
        raise HTTPException(status_code=401, detail="Invalid authentication payload")
    return user_id


@router.post("/tts/enable")
async def enable_tts(current_user: Dict[str, Any] = Depends(get_current_user_or_internal)):
    """Enable TTS for current actor."""
    try:
        user_id = _actor_user_id(current_user)
        _tts_states[user_id] = {"enabled": True}
        logger.info("TTS enabled for user %s", user_id)
        return {"success": True, "message": "TTS enabled"}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error enabling TTS")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/tts/disable")
async def disable_tts(current_user: Dict[str, Any] = Depends(get_current_user_or_internal)):
    """Disable TTS for current actor."""
    try:
        user_id = _actor_user_id(current_user)
        _tts_states[user_id] = {"enabled": False}
        logger.info("TTS disabled for user %s", user_id)
        return {"success": True, "message": "TTS disabled"}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error disabling TTS")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/tts/status")
async def get_tts_status(current_user: Dict[str, Any] = Depends(get_current_user_or_internal)):
    """Get TTS status for current actor."""
    try:
        user_id = _actor_user_id(current_user)
        tts_state = _tts_states.get(user_id, {"enabled": False})
        return {
            "success": True,
            "enabled": tts_state.get("enabled", False),
            "status": tts_state,
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting TTS status")
        raise HTTPException(status_code=500, detail="Internal server error")


