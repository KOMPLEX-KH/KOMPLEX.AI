from fastapi import APIRouter, HTTPException, Header
from app.instructions.general_preprompt import general_pre_prompt
from app.instructions.topic_preprompt import topic_pre_prompt
from app.models.ask_request import AskRequest
from app.models.gemini_response_schema import GeminiResponseSchema
from app.utils import parse_response_type
from app.core import setting
from app.core.gemini import call_gemini

router = APIRouter()


@router.post("/gemini", response_model=GeminiResponseSchema)
def explain_gemini( 
    body: AskRequest, x_api_key: str = Header(..., alias="X-API-Key")
):
    try:
        if x_api_key != setting.INTERNAL_API_KEY:
            raise HTTPException(status_code=401, detail="Unauthorized")

        if not body.prompt:
            raise HTTPException(status_code=400, detail="Prompt is required")

        response_type = parse_response_type(body.response_type)
        prompt_text = general_pre_prompt(body.prompt, body.previous_context, response_type)
        response = call_gemini(prompt_text)

        return GeminiResponseSchema(result=response)
    except HTTPException:
        raise HTTPException(status_code=400, detail="Invalid request")


@router.post("/topic/gemini", response_model=GeminiResponseSchema)
def explain_topic(
    body: AskRequest, x_api_key: str = Header(..., alias="X-API-Key")
):
    try:
        if x_api_key != setting.INTERNAL_API_KEY:
            raise HTTPException(status_code=401, detail="Invalid or missing API key")

        if not body.prompt or not body.topic_content:
            raise HTTPException(
                status_code=400, detail="Prompt and topic content are required"
            )
        response_type = parse_response_type(body.response_type)
        prompt_text = topic_pre_prompt(
            body.prompt, body.topic_content, body.previous_context, response_type
        )
        response = call_gemini(prompt_text)

        return GeminiResponseSchema(result=response)
    except HTTPException:
        raise HTTPException(status_code=400, detail="Invalid request")
