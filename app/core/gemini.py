from google import genai
from app.core.config import setting

client = genai.Client(api_key=setting.GEMINI_API_KEY)

def call_gemini(prompt: str) -> str:
    response = client.models.generate_content(
        model="gemini-2.5-flash", contents=prompt
    )
    return response.text
