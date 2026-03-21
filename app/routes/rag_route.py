import logging
from fastapi import APIRouter, HTTPException, Header, Request
from app.models.ask_request import AskRequest
from app.core.config import setting
from app.utils import parse_response_type
from app.models.response_schema import ResponseSchema

router = APIRouter()
logger = logging.getLogger("complex.rag")

@router.post("/ask")
async def ask_endpoint(
    body: AskRequest,
    request: Request,
    x_api_key: str = Header(None),
    x_rag_debug: str = Header(None, alias="X-RAG-Debug"),
):
    if x_api_key != setting.INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    rag_service = getattr(request.app.state, "rag_service", None)
    if rag_service is None:
        raise HTTPException(status_code=503, detail="RAG service not ready")

    if not body.prompt.strip():
        raise HTTPException(status_code=400, detail="Empty prompt not allowed")

    response_type = parse_response_type(body.response_type)

    debug = (
        str(x_rag_debug).strip().lower() in {"1", "true", "yes", "on"}
        if x_rag_debug is not None
        else False
    )

    logger.info(
        "[RAG/REQ] responseType=%s debug=%s promptChars=%d promptPreview=%r",
        response_type.value,
        debug,
        len(body.prompt),
        body.prompt[:120],
    )

    try:
        answer, _ranked_docs, _debug_info = await rag_service.ask_async(
            body.prompt,
            response_type=response_type,
            previous_context=body.previous_context,
            debug=debug,
        )
        return ResponseSchema(result=answer)
    except Exception as exc:
        logger.exception("Error in /ask")
        raise HTTPException(
            status_code=500,
            detail="អធ្យាស្រ័យខ្ញុំមិនអាចជួយបានទេ (កំហុសក្នុងការឆ្លើយតប)",
        ) from exc
