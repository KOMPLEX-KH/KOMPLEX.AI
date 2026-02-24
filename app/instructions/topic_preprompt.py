from typing import Optional

from app.instructions.templates import (
    PromptTemplate,
    TopicKomplexPrompt,
    TopicNormalPrompt,
)
from app.models.reponse_type import ResponseType


def _get_topic_template(response_type: ResponseType) -> PromptTemplate:
    if response_type == ResponseType.KOMPLEX:
        return TopicKomplexPrompt()
    return TopicNormalPrompt()


def topic_pre_prompt(
    prompt: str,
    topic_content: str,
    previous_context: Optional[str],
    response_type: ResponseType,
) -> str:
    template = _get_topic_template(response_type)
    return template.build(prompt, previous_context or "គ្មានព័ត៌មានមុន", topic_content)
