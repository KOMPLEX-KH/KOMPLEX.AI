from enum import Enum
import logging
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, Request, Header, HTTPException
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv
import os
import google.generativeai as genai
from pydantic import BaseModel

from .instructions.general_preprompt import pre_prompt
from .instructions import topic_preprompt_box, topic_preprompt_md
from .rag_service import RAGService

# Set up ================================================================================================

# Load env variables
load_dotenv()

# Configure API key
api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY not set in environment")

genai.configure(api_key=api_key)

INTERNAL_KEY = os.getenv("INTERNAL_API_KEY")
if not INTERNAL_KEY:
    raise ValueError("INTERNAL_API_KEY not set in environment")

app = FastAPI()

# Create model once at startup
model = genai.GenerativeModel("gemini-2.5-flash")

# Initialize RAG service (lazy load on first use)
rag_service = RAGService()

def get_rag_service() -> RAGService:
    """Get initialized RAG service."""
    global rag_service
    if rag_service is None:  # defensive; should be set on startup
        rag_service = RAGService()
    return rag_service

# ========================================================================================================================

class ResponseType(str, Enum):
    KOMPLEX = "komplex"
    NORMAL = "normal"


def _parse_response_type(raw_response_type: str | None) -> ResponseType:
    if raw_response_type is None:
        return ResponseType.NORMAL
    try:
        return ResponseType(raw_response_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid responseType") from exc


def _build_topic_prompt(
    response_type: ResponseType, prompt: str, topic_content, previous_context: str | None
) -> str:
    if response_type == ResponseType.KOMPLEX:
        return topic_preprompt_box.topic_pre_prompt(
            prompt, topic_content, previous_context
        )
    return topic_preprompt_md.topic_pre_prompt(prompt, topic_content, previous_context)


@app.post("/gemini")
async def explain_ai(
    request: Request,
    x_api_key: str = Header(None),  # Expecting a header like:  X-API-Key: <key>
):
    if x_api_key != INTERNAL_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    data = await request.json()
    prompt = data.get("prompt")
    raw_response_type = data.get("responseType")
    previous_context = data.get("previousContext")

    if not prompt:
        return {"error": "Missing prompt"}

    response_type = _parse_response_type(raw_response_type)
    prompt_text = pre_prompt(prompt, previous_context, response_type)
    response = model.generate_content(prompt_text)

    return {"result": response.text}

# ========================================================================================================================
    
@app.post("/topic/gemini")
async def explain_topic(
    request: Request,
    x_api_key: str = Header(None),  # Expecting a header like:  X-API-Key: <key>
):
    if x_api_key != INTERNAL_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    data = await request.json()
    prompt = data.get("prompt")
    topic_content = data.get("topicContent")
    previous_context = data.get("previousContext")
    raw_response_type = data.get("responseType")

    if not prompt or not topic_content:
        return {"error": "Missing prompt or topicContent"}

    response_type = _parse_response_type(raw_response_type)
    prompt_text = _build_topic_prompt(response_type, prompt, topic_content, previous_context)
    response = model.generate_content(prompt_text)

    return {"result": response.text}

# ========================================================================================================================

def _find_docs_folder() -> Optional[Path]:
    """Find docs folder: first next to this file, then project_root/src/docs."""
    _src_dir = Path(__file__).resolve().parent
    candidate = _src_dir / "docs"
    if candidate.exists():
        return candidate
    # Fallback: project root might be parent of src (e.g. when run from app/)
    for parent in _src_dir.parents:
        src_docs = parent / "src" / "docs"
        if src_docs.exists():
            return src_docs
    return None


@app.on_event("startup")
async def startup_event():
    global rag_service
    _src_dir = Path(__file__).resolve().parent
    _persist_dir = str(_src_dir / "chroma_db")
    rag_service = RAGService(persist_directory=_persist_dir)
    await rag_service.init_redis()

    DOCS_FOLDER = _find_docs_folder()
    if DOCS_FOLDER is None:
        logging.warning("Docs folder not found (looked next to src and src/docs). RAG will have no documents.")
        return
    try:
        rag_service.load_documents_from_folder(str(DOCS_FOLDER))
        num_docs = len(rag_service.docs)
        logging.info("Docs folder: %s — loaded %s document(s)", DOCS_FOLDER, num_docs)
        if num_docs > 0:
            rag_service.create_vector_store()
            logging.info("RAG service ready with documents.")
        else:
            logging.warning("No .txt files in docs folder; RAG service has no documents.")
    except Exception as e:
        logging.exception("Startup failed loading docs or creating vector store: %s", e)
        # rag_service stays with no docs; retriever will return nothing

# -------------------------------
# /ask endpoint
# -------------------------------
class AskRequest(BaseModel):
    prompt: str
    responseType: str | None = None
    previousContext: str | None = None

@app.get("/rag-status")
async def rag_status(x_api_key: str = Header(None)):
    """Return RAG state so you can see why retrieval might be empty. Requires X-API-Key."""
    if x_api_key != INTERNAL_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if rag_service is None:
        return {"ok": False, "error": "RAG service not initialized"}
    test_error = None
    try:
        test_docs = await rag_service.hybrid_retrieve_async("ស៊ីមណូស្ពែម", top_k=2)
        test_count = len(test_docs)
    except Exception as e:
        test_count = None
        test_error = str(e)
    out = {
        "ok": True,
        "docs_loaded": len(rag_service.docs),
        "chunks": len(rag_service.chunks),
        "retriever_ready": rag_service.retriever is not None,
        "bm25_ready": rag_service.bm25 is not None,
        "test_retrieval_count": test_count,
    }
    if test_error is not None:
        out["test_retrieval_error"] = test_error
    return out


@app.post("/ask")
async def ask_endpoint(payload: AskRequest, x_api_key: str = Header(None)):
    if x_api_key != INTERNAL_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")
    if rag_service is None:
        raise HTTPException(status_code=503, detail="RAG service not ready")
    if not payload.prompt.strip():
        raise HTTPException(status_code=400, detail="Empty prompt not allowed")

    async def generator():
        try:
            async for chunk in rag_service.stream_answer_async(payload.prompt):
                yield chunk
        except Exception:
            logging.exception("Error in streaming")
            yield "I don’t know based on the documents."

    return StreamingResponse(generator(), media_type="text/plain")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("src.main:app", host="0.0.0.0", port=port)
    