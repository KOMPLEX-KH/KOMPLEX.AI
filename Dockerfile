# Small FastAPI service that forwards prompts to Gemini (no local models, no GPU)
FROM python:3.13-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY src ./src
RUN useradd --uid 10001 --no-create-home app
USER app
EXPOSE 8000
# one worker keeps memory low; requests are I/O-bound (waiting on Gemini)
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--no-access-log"]
