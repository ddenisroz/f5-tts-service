from typing import Any, Dict, List
import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from auth import get_current_user_or_internal
from database import UserVoiceEnabled, Voice as VoiceModel, get_db

logger = logging.getLogger(__name__)

voice_enabled_router = APIRouter(prefix="/user/voices/enabled", tags=["voice-enabled"])


def _ensure_user_access(current_user: Dict[str, Any], target_user_id: int) -> None:
    actor_user_id = current_user.get("user_id", current_user.get("id"))
    if current_user.get("is_admin"):
        return
    if not isinstance(actor_user_id, int) or actor_user_id != target_user_id:
        raise HTTPException(status_code=403, detail="Access denied")


@voice_enabled_router.get("/{user_id}")
async def get_user_enabled_voices(
    user_id: int,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user_or_internal),
):
    """Return enabled voice IDs for the user."""
    try:
        _ensure_user_access(current_user, user_id)

        enabled_records = db.query(UserVoiceEnabled).filter(
            UserVoiceEnabled.user_id == user_id,
            UserVoiceEnabled.is_enabled.is_(True),
        ).all()

        if not enabled_records:
            all_voices = db.query(VoiceModel).filter(VoiceModel.is_active.is_(True)).all()
            enabled_voice_ids = [voice.id for voice in all_voices]
            logger.info(
                "No enabled voices for user %s, returning all active voices (%s)",
                user_id,
                len(enabled_voice_ids),
            )
        else:
            enabled_voice_ids = [record.voice_id for record in enabled_records]
            logger.info("Found %s enabled voices for user %s", len(enabled_voice_ids), user_id)

        return {"success": True, "enabled_voice_ids": enabled_voice_ids}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error getting enabled voices for user %s", user_id)
        raise HTTPException(status_code=500, detail="Internal server error")


@voice_enabled_router.post("/{user_id}")
async def update_user_enabled_voices(
    user_id: int,
    voice_ids: List[int],
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user_or_internal),
):
    """Replace enabled voices list for the user."""
    try:
        _ensure_user_access(current_user, user_id)

        all_voices = db.query(VoiceModel).filter(VoiceModel.is_active.is_(True)).all()
        all_voice_ids = {voice.id for voice in all_voices}
        provided_voice_ids = set(voice_ids)

        invalid_ids = provided_voice_ids - all_voice_ids
        if invalid_ids:
            raise HTTPException(status_code=400, detail=f"Invalid voice IDs: {sorted(invalid_ids)}")

        db.query(UserVoiceEnabled).filter(UserVoiceEnabled.user_id == user_id).delete()

        for voice_id in all_voice_ids:
            db.add(
                UserVoiceEnabled(
                    user_id=user_id,
                    voice_id=voice_id,
                    is_enabled=voice_id in provided_voice_ids,
                )
            )

        db.commit()
        logger.info(
            "Updated enabled voices for user %s: %s of %s",
            user_id,
            len(provided_voice_ids),
            len(all_voice_ids),
        )
        return {
            "success": True,
            "message": f"Enabled voices updated: {len(provided_voice_ids)} voices enabled",
        }
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error updating enabled voices for user %s", user_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


@voice_enabled_router.put("/{user_id}/{voice_id}")
async def toggle_voice_enabled(
    user_id: int,
    voice_id: int,
    is_enabled: bool,
    db: Session = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user_or_internal),
):
    """Toggle one voice enabled/disabled for the user."""
    try:
        _ensure_user_access(current_user, user_id)

        voice = db.query(VoiceModel).filter(
            VoiceModel.id == voice_id,
            VoiceModel.is_active.is_(True),
        ).first()
        if not voice:
            raise HTTPException(status_code=404, detail="Voice not found")

        record = db.query(UserVoiceEnabled).filter(
            UserVoiceEnabled.user_id == user_id,
            UserVoiceEnabled.voice_id == voice_id,
        ).first()

        if record:
            record.is_enabled = is_enabled
        else:
            db.add(UserVoiceEnabled(user_id=user_id, voice_id=voice_id, is_enabled=is_enabled))

        db.commit()
        logger.info("Voice %s for user %s set to %s", voice_id, user_id, is_enabled)
        return {"success": True, "message": "Voice state updated successfully"}
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error toggling voice %s for user %s", voice_id, user_id)
        db.rollback()
        raise HTTPException(status_code=500, detail="Internal server error")


