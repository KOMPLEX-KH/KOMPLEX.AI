from app.models.reponse_type import ResponseType

def parse_response_type(raw_response_type: str | None) -> ResponseType:
    if raw_response_type is None or raw_response_type.lower() == "normal":
        return ResponseType.NORMAL
    return ResponseType.KOMPLEX