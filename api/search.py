from typing import Annotated
from fastapi import APIRouter, File, UploadFile, HTTPException, status
from core.main import audio_track_similaries

router = APIRouter(prefix='/search', tags=["search"])

@router.post('')
async def api_new_search(audioTrack: Annotated[UploadFile, File(...)]):
    
    if audioTrack.content_type != "audio/mpeg":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El archivo debe ser un audio en formato MP3 (audio/mpeg)."
        )

    return await audio_track_similaries(audio_track=audioTrack)