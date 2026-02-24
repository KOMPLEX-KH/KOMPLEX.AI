from app.instructions.templates import GeneralKomplexPrompt, GeneralNormalPrompt
from app.models.reponse_type import ResponseType


def _get_general_template(response_type: ResponseType):
    if response_type == ResponseType.KOMPLEX:
        return GeneralKomplexPrompt()
    return GeneralNormalPrompt()


def general_pre_prompt(
    prompt: str,
    previous_context: str | None,
    response_type: ResponseType,
) -> str:
    template = _get_general_template(response_type)
    return template.build(prompt, previous_context or "គ្មានព័ត៌មានមុន")
