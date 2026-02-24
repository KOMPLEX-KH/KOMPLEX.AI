from app.instructions.templates import GeneralKomplexPrompt, GeneralNormalPrompt
from app.models.komplex_reponse_type import KomplexResponseType


def _get_general_template(response_type: KomplexResponseType):
    if response_type == KomplexResponseType.KOMPLEX:
        return GeneralKomplexPrompt()
    return GeneralNormalPrompt()


def general_pre_prompt(
    prompt: str,
    previous_context: str | None,
    response_type: KomplexResponseType,
) -> str:
    template = _get_general_template(response_type)
    return template.build(prompt, previous_context or "គ្មានព័ត៌មានមុន")
