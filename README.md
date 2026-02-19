# KOMPLEX.AI

A FastAPI-based educational AI service providing both standard Gemini-powered explanations and Retrieval-Augmented Generation (RAG) capabilities for domain-specific knowledge retrieval. Designed for Khmer language educational content with support for structured TopicContent_V3 JSON output and markdown formatting.

## Table of Contents

- [Overview](#overview)
- [Project Structure](#project-structure)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Application](#running-the-application)
- [API Endpoints](#api-endpoints)
- [RAG System](#rag-system)
- [Development](#development)

## Overview

KOMPLEX.AI provides two main capabilities:

1. **Standard AI Endpoints** (`/gemini`, `/topic/gemini`): Direct Gemini API integration with custom prompt engineering for educational content generation in Khmer language.

2. **RAG Endpoint** (`/ask`): Retrieval-Augmented Generation system that grounds responses in a document knowledge base, enabling accurate answers based on provided curriculum documents.

The system supports two response formats:
- **Komplex**: Structured TopicContent_V3 JSON format for rich educational content
- **Normal**: Markdown-formatted responses

## Project Structure

```
KOMPLEX.AI/
├── app/
│   ├── app.py                 # FastAPI application entry point
│   ├── core/
│   │   ├── config.py          # Configuration and settings
│   │   └── gemini.py          # Gemini API client
│   ├── docs/                  # Document storage for RAG
│   │   └── biology.txt        # Example knowledge base
│   ├── instructions/
│   │   ├── general_preprompt.py      # Prompt engineering logic
│   │   ├── topic_preprompt_box.py    # Komplex format prompts
│   │   └── topic_preprompt_md.py     # Markdown format prompts
│   ├── models/
│   │   ├── ask_request.py            # RAG request model
│   │   ├── gemini_body.py            # Gemini request model
│   │   ├── gemini_response_type.py   # Response type model
│   │   └── komplex_reponse_type.py   # Komplex response enum
│   ├── rag/
│   │   └── rag_service.py     # RAG service implementation
│   ├── routes/
│   │   ├── ai_route.py        # Standard AI endpoints
│   │   └── rag_route.py       # RAG endpoint
│   └── utils/
│       └── parse__response_type.py   # Response type parser
├── chroma_db/                 # Vector database storage (auto-generated)
├── main.py                    # Application runner
├── pyproject.toml             # Project dependencies and metadata
├── uv.lock                    # Dependency lock file
└── RAG_IMPLEMENTATION_GUIDE.md  # Complete RAG documentation
```

## Installation

### Prerequisites

- Python 3.13 or higher
- pip or uv package manager

### Step 1: Clone the Repository

```bash
git clone <repository-url>
cd KOMPLEX.AI
```

### Step 2: Create Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### Step 3: Install Dependencies

**Using pip:**
```bash
pip install -e .
```

**Using uv (recommended):**
```bash
uv pip install -e .
```

The project uses `pyproject.toml` for dependency management. All required packages will be installed automatically.

### Step 4: Verify Installation

```bash
python -c "import fastapi, uvicorn, google.genai; print('Dependencies installed successfully')"
```

## Configuration

Create a `.env` file in the project root with the following variables:

```env
PORT=8000
HOST=0.0.0.0
GEMINI_API_KEY=your_gemini_api_key_here
INTERNAL_API_KEY=your_internal_api_key_here
HF_TOKEN_KEY=your_huggingface_token_here
TRANSLATE_API_URL=your_translate_api_url
USERNAME_TRANSLATE_API=your_username
PASSWORD_TRANSLATE_API=your_password
```

**Required variables:**
- `GEMINI_API_KEY`: Google Gemini API key for LLM access
- `INTERNAL_API_KEY`: API key for endpoint authentication

**Optional variables:**
- `PORT`: Server port (default: 8000)
- `HOST`: Server host (default: 0.0.0.0)
- `HF_TOKEN_KEY`: HuggingFace token for embedding models
- `TRANSLATE_API_URL`, `USERNAME_TRANSLATE_API`, `PASSWORD_TRANSLATE_API`: Translation service credentials

## Running the Application

### Development Mode

```bash
python main.py
```

This starts the server with auto-reload enabled on `http://127.0.0.1:8000`.

### Production Mode

```bash
uvicorn app.app:app --host 0.0.0.0 --port 8000
```

### Using Custom Port

```bash
PORT=8080 uvicorn app.app:app --host 0.0.0.0
```

### Verify Server is Running

Access the interactive API documentation at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## API Endpoints

### Standard AI Endpoints

#### POST `/gemini`

Standard Gemini-powered explanation endpoint with custom prompt engineering.

**Headers:**
```
X-API-Key: <your_internal_api_key>
Content-Type: application/json
```

**Request Body:**
```json
{
  "prompt": "តើស៊ីមណូស្ពែមជាអ្វី?",
  "rawResponseType": "normal",
  "previousContext": ""
}
```

**Fields:**
- `prompt` (string, required): The user's question or request
- `rawResponseType` (string, optional): Response format - `"komplex"` or `"normal"` (default: `"normal"`)
- `previousContext` (string, optional): Previous conversation context

**Response:**
```json
{
  "result": "Generated explanation in Khmer..."
}
```

**Prompt Engineering:**
- For `"normal"` type: Generates markdown-formatted responses with proper spacing, headings, and math equations
- For `"komplex"` type: Generates TopicContent_V3 JSON structure with definition boxes, tips, examples, and graphs
- Both formats enforce Khmer-only language, academic subject restrictions, and professional tone

#### POST `/topic/gemini`

Topic-specific explanation endpoint with additional topic content context.

**Headers:**
```
X-API-Key: <your_internal_api_key>
Content-Type: application/json
```

**Request Body:**
```json
{
  "prompt": "Explain photosynthesis",
  "rawResponseType": "komplex",
  "previousContext": "",
  "topicContent": "Additional topic context..."
}
```

**Fields:**
- `prompt` (string, required): The user's question
- `rawResponseType` (string, optional): Response format
- `previousContext` (string, optional): Previous conversation context
- `topicContent` (string, required): Additional topic-specific content to include in context

**Response:**
```json
{
  "result": "Generated explanation..."
}
```

### RAG Endpoint

#### POST `/ask`

Retrieval-Augmented Generation endpoint that grounds responses in document knowledge base.

**Headers:**
```
X-API-Key: <your_internal_api_key>
Content-Type: application/json
```

**Request Body:**
```json
{
  "prompt": "តើស៊ីមណូស្ពែមជាអ្វី?",
  "responseType": "normal",
  "previousContext": ""
}
```

**Fields:**
- `prompt` (string, required): The user's question
- `responseType` (string, optional): Currently unused, reserved for future use
- `previousContext` (string, optional): Currently unused, reserved for future use

**Response:**
- Content-Type: `text/plain`
- Streaming: Response is streamed as text chunks
- Fallback: Returns `"អធ្យាស្រ័យខ្ញុំមិនអាចជួយបានទេ"` if no relevant context is found

**How it works:**
1. Query is processed through hybrid retrieval (semantic vector search + BM25 keyword search)
2. Retrieved document chunks are reranked by relevance
3. Context is assembled into a prompt instructing the model to answer only from provided context
4. Response is generated and streamed back

For complete RAG implementation details, see [RAG_IMPLEMENTATION_GUIDE.md](./RAG_IMPLEMENTATION_GUIDE.md).

## RAG System

The RAG (Retrieval-Augmented Generation) system enables domain-specific question answering by:

1. **Document Indexing**: On startup, documents in `app/docs/` are loaded, chunked, and embedded
2. **Hybrid Retrieval**: Combines semantic search (vector embeddings) with keyword search (BM25)
3. **Reranking**: Uses LLM to reorder retrieved chunks by relevance
4. **Context-Aware Generation**: Injects retrieved context into prompts to ground responses

**Key Components:**
- **Vector Store**: Chroma DB for persistent embedding storage
- **Embedding Model**: `sentence-transformers/all-MiniLM-L6-v2` (384-dimensional vectors)
- **Chunking**: 900-character chunks with 150-character overlap
- **Retrieval**: Top-K retrieval (default: 6 chunks)

**Document Setup:**
- Place `.txt` files in `app/docs/` directory
- Documents are automatically loaded and indexed on server startup
- Vector store persists to `chroma_db/` directory

For comprehensive RAG documentation including architecture, flow diagrams, technical details, and use cases, refer to [RAG_IMPLEMENTATION_GUIDE.md](./RAG_IMPLEMENTATION_GUIDE.md).

## Development

### Project Dependencies

Dependencies are managed via `pyproject.toml`. Key packages include:

- `fastapi`: Web framework
- `uvicorn`: ASGI server
- `google-genai`: Gemini API client
- `langchain`, `langchain-community`, `langchain-chroma`: RAG framework
- `chromadb`: Vector database
- `sentence-transformers`: Embedding models
- `rank-bm25`: Keyword search
- `redis`: Memory storage (currently disabled)

### Adding New Documents

1. Place `.txt` files in `app/docs/`
2. Restart the server - documents will be automatically indexed
3. To rebuild the vector store, delete `chroma_db/` directory and restart

### Code Structure

- **Routes**: API endpoint definitions in `app/routes/`
- **Models**: Pydantic models for request/response validation in `app/models/`
- **Core**: Configuration and external service clients in `app/core/`
- **Instructions**: Prompt engineering logic in `app/instructions/`
- **RAG**: RAG service implementation in `app/rag/`

### Testing Endpoints

**Using cURL:**
```bash
curl -X POST "http://localhost:8000/gemini" \
  -H "X-API-Key: your_internal_api_key" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "តើស៊ីមណូស្ពែមជាអ្វី?", "rawResponseType": "normal"}'
```

**Using Python:**
```python
import requests

response = requests.post(
    "http://localhost:8000/ask",
    headers={
        "X-API-Key": "your_internal_api_key",
        "Content-Type": "application/json"
    },
    json={"prompt": "តើស៊ីមណូស្ពែមជាអ្វី?"},
    stream=True
)

for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
    print(chunk, end="")
```