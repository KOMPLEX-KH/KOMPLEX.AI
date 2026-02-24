from typing import Any, Optional

from app.instructions.templates import (
    PromptTemplate,
    TopicKomplexPrompt,
    TopicNormalPrompt,
)
from app.models.komplex_reponse_type import KomplexResponseType


def _get_topic_template(response_type: KomplexResponseType) -> PromptTemplate:
    if response_type == KomplexResponseType.KOMPLEX:
        return TopicKomplexPrompt()
    return TopicNormalPrompt()


def topic_pre_prompt(
    prompt: str,
    topic_content: Any,
    previous_context: Optional[str],
    response_type: KomplexResponseType,
) -> str:
    template = _get_topic_template(response_type)
    return template.build(prompt, previous_context or "គ្មានព័ត៌មានមុន", topic_content)
