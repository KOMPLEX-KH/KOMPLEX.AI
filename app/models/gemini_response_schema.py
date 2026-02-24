from pydantic import BaseModel

class GeminiResponseSchema(BaseModel):
    result: str