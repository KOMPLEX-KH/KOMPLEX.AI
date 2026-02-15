# RAG Service Documentation

## Purpose

The RAG (Retrieval-Augmented Generation) service augments a Large Language Model (Gemini) with a document knowledge base. It enables **context-aware question answering** over custom text documents—specifically designed for the **KOMPLEX.AI** educational platform to answer biology (and other academic) questions grounded in the provided curriculum (e.g., Khmer biology content in `src/docs/`).

Instead of relying solely on the model's pre-trained knowledge, the service:

- Loads and indexes your documents
- Retrieves the most relevant chunks for each query
- Reranks them with the LLM for relevance
- Injects that context into the prompt so answers stay faithful to your documents

---

## Usage

### Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Set environment variables (create a .env file)
GEMINI_API_KEY=your_gemini_api_key
INTERNAL_API_KEY=your_internal_api_key

# 3. Start the server
python -m src.main
# or
uvicorn src.main:app --reload --port 8000
```

### RAG Endpoint: `POST /ask`

The RAG pipeline is exposed via the `/ask` endpoint.

**Headers**

| Header      | Required | Description                         |
|-------------|----------|-------------------------------------|
| `X-API-Key` | Yes      | Must match `INTERNAL_API_KEY`       |
| `Content-Type` | Yes   | `application/json`                  |

**Request Body**

```json
{
  "prompt": "តើស៊ីមណូស្ពែមជាអ្វី?",
  "responseType": "khmer",
  "previousContext": ""
}
```

| Field            | Type   | Required | Description                                   |
|------------------|--------|----------|-----------------------------------------------|
| `prompt`         | string | Yes      | The user's question                           |
| `responseType`   | string | No       | `"normal"` \| `"komplex"` (currently unused)  |
| `previousContext`| string | No       | Previous conversation context (currently unused) |

**Response**

- **Content-Type:** `text/plain`
- **Streaming:** Response is streamed as text chunks.
- **Fallback:** On error or missing context, returns: `អធ្យាស្រ័យខ្ញុំមិនអាចជួយបានទេ` (Khmer: "Sorry, I can't help").

**Example (cURL)**

```bash
curl -X POST "http://localhost:8000/ask" \
  -H "X-API-Key: your_internal_api_key" \
  -H "Content-Type: application/json" \
  -d '{"prompt": "តើស៊ីមណូស្ពែមមានប៉ុន្មានប្រភេទ?"}'
```

**Example (Python)**

```python
import requests

response = requests.post(
    "http://localhost:8000/ask",
    headers={
        "X-API-Key": "your_internal_api_key",
        "Content-Type": "application/json",
    },
    json={"prompt": "តើស៊ីមណូស្ពែមមានប៉ុន្មានប្រភេទ?"},
    stream=True,
)
for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
    print(chunk, end="")
```

### Document Setup

- Place `.txt` files in `src/docs/` (e.g., `src/docs/biology.txt`).
- On server **startup**, documents are loaded, chunked, embedded, and indexed.
- Vector store is persisted in `src/chroma_db/`.

To rebuild after adding or changing documents:

```bash
rm -r src/chroma_db
python -m src.main
```

---

## Process Workflow

High-level flow from startup to answering a question:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           STARTUP (main.py startup_event)                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  1. RAGService() instantiated                                                │
│  2. init_redis() called (currently no-op; Redis disabled)                    │
│  3. load_documents_from_folder("src/docs") → TextLoader → LangChain Document │
│  4. create_vector_store() → chunk → embed → Chroma + BM25 index              │
└─────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                     REQUEST: POST /ask  { "prompt": "..." }                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        stream_answer_async(prompt)                           │
│                        (delegates to ask_async)                              │
└─────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  1. HYBRID RETRIEVAL                                                         │
│     • Vector: Chroma (sentence-transformers embeddings) → top_k chunks       │
│     • BM25: rank_bm25 lexical search → top_k chunks                          │
│     • Merge by id_hash, take top_k unique chunks                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  2. RERANK                                                                   │
│     • Gemini prompted to rank chunks by relevance to the question            │
│     • Returns ordered list of chunk indexes → reorder docs                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  3. MEMORY CONTEXT                                                           │
│     • summarize_memory() → currently empty (Redis disabled)                  │
└─────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  4. PROMPT ASSEMBLY                                                          │
│     • MEMORY: (empty for now)                                                │
│     • CONTEXT: concatenated ranked chunks                                    │
│     • QUESTION: user prompt                                                  │
│     • Instructs model to answer ONLY from context; fallback message if not   │
└─────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  5. GENERATION                                                               │
│     • model.generate_content(prompt) via Gemini 2.5 Flash                    │
│     • answer extracted from response.text                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  6. MEMORY UPDATE                                                            │
│     • update_memory(query, answer) → currently no-op (Redis disabled)        │
└─────────────────────────────────────────────────────────────────────────────┘
                                         │
                                         ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│  7. STREAM RESPONSE                                                          │
│     • Full answer yielded as single chunk (no token-level streaming yet)     │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Flow summary**

| Step | Component | Location |
|------|-----------|----------|
| Document load | LangChain `TextLoader` | `rag_service.load_documents_from_folder` |
| Chunking | `RecursiveCharacterTextSplitter` | `rag_service.create_vector_store` |
| Embedding | HuggingFace `all-MiniLM-L6-v2` | `rag_service` |
| Vector store | Chroma (persisted) | `rag_service.vector_store` |
| Lexical retrieval | BM25 | `rag_service._hybrid_retrieve` |
| Reranking | Gemini 2.5 Flash | `rag_service.rerank_blocking` |
| Generation | Gemini 2.5 Flash | `rag_service.ask_async` |

---

## Technology & Dependencies

### Core Stack

| Component | Technology | Purpose |
|-----------|------------|---------|
| API | FastAPI | REST API and streaming |
| ASGI server | Uvicorn | Run FastAPI app |
| LLM | Google Gemini 2.5 Flash | Reranking + answer generation |
| Embeddings | HuggingFace `sentence-transformers/all-MiniLM-L6-v2` | Dense embeddings for vector search |
| Vector DB | Chroma | Persistent vector store |
| RAG framework | LangChain | Loaders, splitters, Chroma integration |
| Lexical search | rank_bm25 (BM25Okapi) | BM25 keyword retrieval |
| Memory (optional) | Redis | Designed for chat memory; currently disabled |

### Libraries (from `requirements.txt`)

- `fastapi` — API framework
- `uvicorn` — ASGI server
- `python-dotenv` — Environment variables
- `google-generativeai` — Gemini API
- `langchain` — RAG orchestration
- `langchain-community` — `TextLoader`, `HuggingFaceEmbeddings`
- `langchain-chroma` — Chroma vector store
- `langchain-core` — Document abstractions
- `chromadb` — Vector database backend
- `sentence-transformers` — Embedding model runtime

### Missing from `requirements.txt`

- **`rank_bm25`** — Required for BM25 retrieval. Add with: `pip install rank_bm25`
- **`redis`** — Optional; only needed if Redis memory is re-enabled

---

## Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `persist_directory` | `./chroma_db` | Chroma persistence path |
| `collection_name` | `"biology"` | Chroma collection name |
| `redis_url` | `redis://localhost:6379` | Redis URL (not used when disabled) |
| `top_k` | 6 | Number of chunks to retrieve and rerank |
| `memory_max` | 10 | Max Q&A pairs in memory (when Redis enabled) |
| `memory_token_limit` | 2000 | Max tokens for memory summary |
| Chunk size | 900 | Characters per chunk |
| Chunk overlap | 150 | Overlap between chunks |

---

## Missing Features & Future Work

### Currently Missing / Incomplete

1. **`responseType` and `previousContext` ignored**  
   `AskRequest` accepts `responseType` and `previousContext` but they are not passed to the RAG service. The prompt does not use response formatting (normal vs. komplex) or prior context.

2. **Dependencies not in `requirements.txt`**  
   - `rank_bm25` is required and must be installed separately.  
   - `redis` is optional but should be listed if memory is re-enabled.

3. **Streaming is simulated**  
   `stream_answer_async` returns the full answer in one chunk, not token-by-token, because the current Gemini `generate_content` usage does not support real streaming.

4. **Redis memory disabled**  
   Chat memory (Q&A history) is implemented but commented out. No conversation context is used across turns.

5. **Limited document formats**  
   Only `.txt` is supported via `TextLoader`. No PDF, DOCX, or Markdown loaders.

6. **Single collection**  
   Only one collection (`"biology"`) is used. No multi-collection or multi-domain support.

7. **No authentication beyond API key**  
   Only `X-API-Key` is checked. No per-user or session-based access control.

8. **No observability**  
   No structured logging, metrics, or tracing for retrieval and generation.

### Future Improvements

| Area | Suggestion |
|------|------------|
| Memory | Re-enable Redis, wire `previousContext` into the prompt |
| Response format | Use `responseType` to switch between markdown and TopicContent_V3 JSON |
| Streaming | Use Gemini streaming API (`generate_content_stream`) for token-level streaming |
| Retrieval | Optional: Cohere/Jina reranker instead of LLM reranking for speed/cost |
| Documents | Add loaders for PDF, DOCX, Markdown, and web content |
| Collections | Support multiple collections (e.g., by subject) with dynamic selection |
| Evaluation | Add retrieval/generation metrics and evaluation scripts |
| Security | Rate limiting, per-user auth, input sanitization |
| Deployment | Docker Compose, optional Redis and health checks |

---

## Related Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /gemini` | Standard Gemini (no RAG, uses preprompt) |
| `POST /topic/gemini` | Topic-specific Gemini with `topicContent` |
| `POST /ask` | RAG-enhanced Q&A over documents |

---

## Troubleshooting

| Issue | Action |
|-------|--------|
| `GEMINI_API_KEY not set` | Set in `.env` or environment |
| `INTERNAL_API_KEY` 401 | Use correct `X-API-Key` header |
| `rank_bm25` ImportError | `pip install rank_bm25` |
| Slow first request | First run loads model and builds index |
| Documents not updating | Delete `src/chroma_db/` and restart |
| Wrong language / style | Adjust RAG prompt in `ask_async` or preprompts in `src/instructions/` |
