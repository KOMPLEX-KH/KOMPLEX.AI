from pydantic_settings import BaseSettings
from dotenv import load_dotenv
load_dotenv()

class Config(BaseSettings):
    PORT: int
    HOST: str
    GEMINI_API_KEY: str
    INTERNAL_API_KEY: str
    HF_TOKEN_KEY: str
    TRANSLATE_API_URL: str
    USERNAME_TRANSLATE_API: str
    PASSWORD_TRANSLATE_API: str

setting = Config() # type: ignore