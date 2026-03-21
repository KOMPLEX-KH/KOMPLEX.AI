from pydantic import BaseModel, Field

class AskRequest(BaseModel):
    prompt: str
    response_type: str | None = Field(default=None, alias="responseType")
    previous_context: str | None = Field(default=None, alias="previousContext")
    topic_content: str | None = Field(default=None, alias="topicContent")
    