from google import genai # type: ignore
from app.core.config import setting

client = genai.Client(api_key=setting.GEMINI_API_KEY) # type: ignore


def call_gemini(prompt: str) -> str:
    response = client.models.generate_content( # type: ignore
        model="gemini-2.5-flash", contents=prompt
    )
    return response.text # type: ignore
