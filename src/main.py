from enum import Enum
from fastapi import FastAPI, Request, Header, HTTPException
from dotenv import load_dotenv
import os
import google.generativeai as genai

from .instructions.general_preprompt import pre_prompt
from .instructions import topic_preprompt_box, topic_preprompt_md
from .rag_service import initialize_rag_service, RAGService

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
rag_service: RAGService | None = None

def get_rag_service() -> RAGService:
    """Lazy initialization of RAG service"""
    global rag_service
    if rag_service is None:
        rag_service = initialize_rag_service(
            docs_folder="docs", 
            collection_name="biology",
            load_all_from_folder=True
        )
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

@app.post("/rag/gemini")
async def explain_with_rag(
    request: Request,
    x_api_key: str = Header(None),  # Expecting a header like:  X-API-Key: <key>
):
    """
    RAG endpoint: Retrieves relevant context from documents and generates response
    """
    if x_api_key != INTERNAL_KEY:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")

    data = await request.json()
    prompt = data.get("prompt")
    raw_response_type = data.get("responseType")
    previous_context = data.get("previousContext")
    k = data.get("k", 4)  # Number of documents to retrieve (default: 4)

    if not prompt:
        return {"error": "Missing prompt"}

    # Get RAG service and retrieve relevant context
    rag = get_rag_service()
    retrieved_context = rag.get_context_from_query(prompt, k=k)

    # Build prompt with retrieved context
    response_type = _parse_response_type(raw_response_type)
    
    # Create enhanced prompt with RAG context
    enhanced_prompt = f"""Based on the following context from the knowledge base:

{retrieved_context}

---

Now answer the following question: {prompt}

{previous_context if previous_context else ""}
"""
    
    prompt_text = pre_prompt(enhanced_prompt, previous_context, response_type)
    response = model.generate_content(prompt_text)

    return {"result": response.text}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("src.main:app", host="0.0.0.0", port=port)
    