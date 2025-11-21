from enum import Enum
from fastapi import FastAPI, Request, Header, HTTPException
from dotenv import load_dotenv
import os
import google.generativeai as genai
import requests
from .instructions.general_preprompt import pre_prompt
from .instructions import topic_preprompt_box, topic_preprompt_md

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

HF_TOKEN_KEY = os.getenv("HF_TOKEN_KEY")
if not HF_TOKEN_KEY:
    raise ValueError("HF_TOKEN_KEY not set in environment")

HF_API_URL = os.getenv("HF_API_URL")
if not HF_API_URL:
    raise ValueError("HF_API_URL not set in environment")

app = FastAPI()

# Create model once at startup
model = genai.GenerativeModel("gemini-2.5-flash")

API_URL = HF_API_URL
headers = {
    "Authorization": f"Bearer {os.environ['HF_TOKEN_KEY']}",
}

# ========================================================================================================================


class ResponseType(str, Enum):
    KOMPLEX = "komplex"
    NORMAL = "normal"


def small_validate(payload):
    response = requests.post(API_URL, headers=headers, json=payload)
    return response.json()


def _parse_response_type(raw_response_type: str | None) -> ResponseType:
    if raw_response_type is None:
        return ResponseType.NORMAL
    try:
        return ResponseType(raw_response_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Invalid responseType") from exc


def _build_topic_prompt(
    response_type: ResponseType,
    prompt: str,
    topic_content,
    previous_context: str | None,
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
    topic = data.get("topic")
    result = small_validate({"inputs": prompt, "parameters": {"candidate_labels": [topic, "general"]}})
    scores = result.get("scores")
    if(scores and scores[0]<0.5 and scores[1]<0.5):
        return {"result": "The provided content is not relevant to the specified topic."}
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
    topic = data.get("topic")
    result = small_validate({"inputs": prompt, "parameters": {"candidate_labels": [topic, "general"]}})
    scores = result.get("scores")
    if(scores and scores[0]<0.5 and scores[1]<0.5):
        return {"result": "The provided content is not relevant to the specified topic."}
    topic_content = data.get("topicContent")
    previous_context = data.get("previousContext")
    raw_response_type = data.get("responseType")

    if not prompt or not topic_content:
        return {"error": "Missing prompt or topicContent"}

    response_type = _parse_response_type(raw_response_type)
    prompt_text = _build_topic_prompt(
        response_type, prompt, topic_content, previous_context
    )
    response = model.generate_content(prompt_text)

    return {"result": response.text}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("src.main:app", host="0.0.0.0", port=port)
