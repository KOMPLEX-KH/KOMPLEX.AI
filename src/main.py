# import re
import os
from enum import Enum
# import requests
# from requests.auth import HTTPBasicAuth
import google.generativeai as genai
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

# from transformers import AutoModelForSeq2SeqLM, AutoTokenizer, pipeline  # COMMENTED OUT

from .instructions import topic_preprompt_box, topic_preprompt_md
from .instructions.general_preprompt import pre_prompt


# Environment & external services ==============================================================================

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise ValueError("GEMINI_API_KEY not set in environment")

genai.configure(api_key=api_key)

INTERNAL_KEY = os.getenv("INTERNAL_API_KEY")
if not INTERNAL_KEY:
    raise ValueError("INTERNAL_API_KEY not set in environment")

# HF_TOKEN_KEY = os.getenv("HF_TOKEN_KEY")
# if not HF_TOKEN_KEY:
#     # If HF_TOKEN_KEY is only needed for models, you can skip this check or remove HF usage
#     pass  # COMMENTED OUT or remove if not used

# COMMENTED OUT: heavy model initializations
# classifier = pipeline(
#     "zero-shot-classification",
#     model="MoritzLaurer/xlm-v-base-mnli-xnli",
# )
#
# model_name = "songhieng/khmer-mt5-summarization"
# summary_tokenizer = AutoTokenizer.from_pretrained(
#     model_name,
#     use_auth_token=HF_TOKEN_KEY,
# )
# summary_model = AutoModelForSeq2SeqLM.from_pretrained(
#     model_name,
#     use_auth_token=HF_TOKEN_KEY,
# )

app = FastAPI()
gemini_model = genai.GenerativeModel("gemini-2.5-flash")


# ========================================================================================================================


class ResponseType(str, Enum):
    KOMPLEX = "komplex"
    NORMAL = "normal"


# class SummarizeRequest(BaseModel):
#     text: str
#     outputType: str


# Helper functions ============================================================================================


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
            prompt,
            topic_content,
            previous_context,
        )
    return topic_preprompt_md.topic_pre_prompt(
        prompt,
        topic_content,
        previous_context,
    )


# def is_khmer(text):
#     pattern = r"[\u1780-\u17FF\u19E0-\u19FF]"
#     return bool(re.search(pattern, text))


# def translate_to_english(text: str) -> str:
#     username = os.getenv("USERNAME_TRANSLATE_API")
#     password = os.getenv("PASSWORD_TRANSLATE_API")
#     url = os.getenv("TRANSLATE_API_URL")

#     if not url or not username or not password:
#         raise ValueError("Translation API credentials are not set in environment")

#     payload = {"input_text": [text], "src_lang": "kh", "tgt_lang": "eng"}

#     response = requests.post(
#         url,
#         json=payload,
#         headers={"Content-Type": "application/json"},
#         auth=HTTPBasicAuth(username, password),
#     )
#     if response.status_code == 200:
#         result = response.json()
#         translated_texts = result.get("translate_text", [])
#         if translated_texts:
#             return translated_texts[0]
#         else:
#             raise ValueError("No translated text found in the response")


@app.get("/ping")
async def ping():
    return {"message": "pong"}


@app.post("/gemini")
async def explain_ai(
    request: Request,
    x_api_key: str = Header(None),
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
    response = gemini_model.generate_content(prompt_text)

    return {"result": response.text}


@app.post("/topic/gemini")
async def explain_topic(
    request: Request,
    x_api_key: str = Header(None),
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

    prompt_text = _build_topic_prompt(
        response_type,
        prompt,
        topic_content,
        previous_context,
    )
    response = gemini_model.generate_content(prompt_text)

    return {"result": response.text}


# COMMENTED OUT: summarization endpoint (heavy)
# @app.post("/summarize")
# async def summarize(
#     request: SummarizeRequest,
#     x_api_key: str = Header(None),
# ):
#     output_type = request.outputType
#     if x_api_key != INTERNAL_KEY:
#         raise HTTPException(status_code=401, detail="Invalid or missing API key")
#     inputs = summary_tokenizer(
#         f"summarize: {request.text}",
#         return_tensors="pt",
#         truncation=True,
#         max_length=512,
#     )
#     length_map = {"summary": 512, "title": 10}
#     output_length = length_map.get(output_type)
#     summary_ids = summary_model.generate(
#         **inputs,
#         max_length=output_length,
#         num_beams=5,
#         length_penalty=2.0,
#         early_stopping=True,
#     )
#     summary = summary_tokenizer.decode(summary_ids[0], skip_special_tokens=True)
#     return {"summary": summary}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("src.main:app", host="0.0.0.0", port=port)
