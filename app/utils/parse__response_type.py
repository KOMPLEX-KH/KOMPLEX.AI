from app.models.reponse_type import ResponseType
from fastapi import HTTPException

def parse_response_type(raw_response_type: str | None) -> ResponseType:
    if raw_response_type is None:
        return ResponseType.NORMAL
    try:
        return ResponseType(raw_response_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid responseType") from exc