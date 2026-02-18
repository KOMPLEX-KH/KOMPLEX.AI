import logging
from fastapi import APIRouter, HTTPException, Header, Request
from fastapi.responses import StreamingResponse
from app.models.ask_request import AskRequest
from app.core.config import setting

router = APIRouter()

@router.post("/ask")
async def ask_endpoint(
    body: AskRequest,
    request: Request,
    x_api_key: str = Header(None),
):
    if x_api_key != setting.INTERNAL_API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")

    rag_service = getattr(request.app.state, "rag_service", None)
    if rag_service is None:
        raise HTTPException(status_code=503, detail="RAG service not ready")

    if not body.prompt.strip():
        raise HTTPException(status_code=400, detail="Empty prompt not allowed")

    async def generator():
        try:
            async for chunk in rag_service.stream_answer_async(body.prompt):
                yield chunk
        except Exception:
            logging.exception("Error in streaming")
            yield "I don't know based on the documents."

    return StreamingResponse(generator(), media_type="text/plain")
