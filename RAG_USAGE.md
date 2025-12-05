# RAG System Usage Guide

## 📋 Setup

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

This will install:
- FastAPI & Uvicorn (API server)
- LangChain & LangChain Community (RAG framework)
- ChromaDB (vector database)
- Sentence Transformers (embeddings)
- Google Generative AI (Gemini API)

### 2. Environment Variables

Make sure you have a `.env` file with:
```
GEMINI_API_KEY=your_gemini_api_key_here
INTERNAL_API_KEY=your_internal_api_key_here
```

### 3. Start the Server

```bash
# From the KOMPLEX.AI directory
python -m src.main

# Or using uvicorn directly
uvicorn src.main:app --reload --port 8000
```

## 🚀 Using the RAG API

### Endpoint: `POST /rag/gemini`

This endpoint uses RAG to retrieve relevant context from your documents before generating a response.

#### Request Headers
```
X-API-Key: your_internal_api_key
Content-Type: application/json
```

#### Request Body
```json
{
  "prompt": "What is photosynthesis?",
  "responseType": "normal",  // optional: "normal" or "komplex"
  "previousContext": null,   // optional: previous conversation context
  "k": 4                     // optional: number of document chunks to retrieve (default: 4)
}
```

#### Example Request (cURL)
```bash
curl -X POST "http://localhost:8000/rag/gemini" \
  -H "X-API-Key: your_internal_api_key" \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Explain how cells divide",
    "responseType": "normal",
    "k": 5
  }'
```

#### Example Request (Python)
```python
import requests

url = "http://localhost:8000/rag/gemini"
headers = {
    "X-API-Key": "your_internal_api_key",
    "Content-Type": "application/json"
}
data = {
    "prompt": "What is DNA?",
    "responseType": "normal",
    "k": 4
}

response = requests.post(url, headers=headers, json=data)
result = response.json()
print(result["result"])
```

#### Example Request (JavaScript/TypeScript)
```javascript
const response = await fetch('http://localhost:8000/rag/gemini', {
  method: 'POST',
  headers: {
    'X-API-Key': 'your_internal_api_key',
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    prompt: 'Explain the process of mitosis',
    responseType: 'normal',
    k: 4
  })
});

const data = await response.json();
console.log(data.result);
```

## 📁 Adding Documents

### Adding Documents to the Knowledge Base

1. **Place your `.txt` files in the `src/docs/` folder**
   - The system automatically loads all `.txt` files from this folder
   - Example: `src/docs/biology.txt`, `src/docs/chemistry.txt`, etc.

2. **First-time setup:**
   - On the first API call to `/rag/gemini`, the system will:
     - Load all `.txt` files from `src/docs/`
     - Split them into chunks
     - Create embeddings
     - Store in ChromaDB (saved in `src/chroma_db/`)

3. **Subsequent uses:**
   - The vector store is persisted in `src/chroma_db/`
   - If you add new documents, delete the `chroma_db` folder to rebuild
   - Or restart the server and it will reload

### Rebuilding the Vector Store

If you add new documents or want to rebuild:

```bash
# Delete the existing vector store
rm -r src/chroma_db

# Restart the server - it will rebuild on first use
python -m src.main
```

## 🔧 Using RAG Service Programmatically

You can also use the RAG service directly in Python:

```python
from src.rag_service import initialize_rag_service

# Initialize RAG service
rag = initialize_rag_service(
    docs_folder="docs",
    collection_name="biology",
    load_all_from_folder=True
)

# Query for relevant documents
query = "What is photosynthesis?"
relevant_docs = rag.retrieve_relevant_docs(query, k=4)

# Get formatted context
context = rag.get_context_from_query(query, k=4)
print(context)

# Get documents with similarity scores
docs_with_scores = rag.retrieve_with_scores(query, k=4)
for doc, score in docs_with_scores:
    print(f"Score: {score:.4f}")
    print(f"Content: {doc.page_content[:200]}...")
```

## 📊 How It Works

1. **Document Loading**: All `.txt` files from `src/docs/` are loaded
2. **Chunking**: Documents are split into chunks of 1000 characters with 200 character overlap
3. **Embedding**: Each chunk is converted to a vector using HuggingFace embeddings
4. **Storage**: Vectors are stored in ChromaDB
5. **Retrieval**: When you query, it finds the most similar document chunks
6. **Generation**: Retrieved context is added to your prompt, then sent to Gemini

## 🎯 Parameters

### `k` Parameter
- Controls how many document chunks to retrieve
- Higher `k` = more context, but potentially less focused
- Lower `k` = more focused, but might miss relevant info
- Default: `4`
- Recommended range: `3-8`

### `responseType` Parameter
- `"normal"`: Standard markdown response
- `"komplex"`: Structured JSON response (TopicContent_V3 format)

## 🧪 Testing

### Test the RAG Endpoint

```python
# test_rag.py
import requests
import json

BASE_URL = "http://localhost:8000"
API_KEY = "your_internal_api_key"

def test_rag():
    response = requests.post(
        f"{BASE_URL}/rag/gemini",
        headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
        json={
            "prompt": "What is the structure of a cell?",
            "responseType": "normal",
            "k": 4
        }
    )
    
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2)}")

if __name__ == "__main__":
    test_rag()
```

## 🔍 Troubleshooting

### Vector Store Not Found
- First API call will create it automatically
- Make sure `src/docs/` contains at least one `.txt` file

### Slow First Request
- First request is slower because it builds the vector store
- Subsequent requests are fast (uses cached vector store)

### Documents Not Updating
- Delete `src/chroma_db/` folder
- Restart the server
- First request will rebuild with new documents

### Import Errors
- Make sure all dependencies are installed: `pip install -r requirements.txt`
- Check Python version (3.8+ required)

## 📝 Example Use Cases

1. **Question Answering**: Ask questions about your documents
2. **Context-Aware Responses**: Get answers based on your specific knowledge base
3. **Document Search**: Find relevant sections from your documents
4. **Educational Content**: Use with biology.txt for biology tutoring

## 🔗 Related Endpoints

- `POST /gemini` - Standard Gemini API (no RAG)
- `POST /topic/gemini` - Topic-specific responses (with topicContent)
- `POST /rag/gemini` - RAG-enhanced responses (with document retrieval)

