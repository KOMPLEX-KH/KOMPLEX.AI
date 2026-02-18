from pydantic import BaseModel

class AskRequest(BaseModel):
    prompt: str
    responseType: str | None = None
    previousContext: str | None = None