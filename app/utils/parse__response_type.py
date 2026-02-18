from app.models.komplex_reponse_type import KomplexResponseType
from fastapi import HTTPException

def parse_response_type(raw_response_type: str | None) -> KomplexResponseType:
    if raw_response_type is None:
        return KomplexResponseType.NORMAL
    try:
        return KomplexResponseType(raw_response_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid responseType") from exc