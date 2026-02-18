from pydantic import BaseModel, Field
from regex import D


class GeminiBody(BaseModel):
    prompt: str = Field(..., alias="prompt")
    raw_response_type: str = Field(..., alias="rawResponseType")
    previous_context: str | None = Field(default=None, alias="previousContext")
    topic_content: str | None = Field(default=None, alias="topicContent")
