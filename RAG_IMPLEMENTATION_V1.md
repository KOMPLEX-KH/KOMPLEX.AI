# RAG Implementation Guide

A comprehensive guide to understanding the Retrieval-Augmented Generation (RAG) system in KOMPLEX.AI, designed for developers coming from a software engineering background.

---

## Table of Contents

1. [Core Concepts](#core-concepts)
2. [What is RAG?](#what-is-rag)
3. [System Architecture](#system-architecture)
4. [Complete Flow Explanation](#complete-flow-explanation)
5. [Technical Implementation Details](#technical-implementation-details)
6. [Use Cases & Examples](#use-cases--examples)
7. [Accuracy vs. Freedom](#accuracy-vs-freedom)
8. [Future Work & Improvements](#future-work--improvements)

---

## Core Concepts

Before diving into the implementation, let's understand the fundamental concepts you'll encounter.

### 1. Embeddings

**What is it?**  
An embedding is a way to convert text into a list of numbers (a vector) that captures the **meaning** of the text, not just the words.

**Analogy:**  
Think of it like GPS coordinates. Instead of saying "near the coffee shop on Main Street," you get precise coordinates like `(40.7128, -74.0060)`. Embeddings do the same for text meaning.

**Example:**
```
Text: "What is photosynthesis?"
Embedding: [0.23, -0.45, 0.67, ..., 0.12]  (384 numbers for this model)

Text: "How do plants make food?"
Embedding: [0.25, -0.43, 0.65, ..., 0.11]  (similar numbers = similar meaning)
```

**Why it matters:**  
Similar texts produce similar embeddings. This lets us find semantically related content even if the exact words differ.

**In this project:**  
- Model: `sentence-transformers/all-MiniLM-L6-v2`
- Output: 384-dimensional vectors
- Purpose: Convert text chunks into searchable vectors

---

### 2. Vector Database (Vector DB)

**What is it?**  
A specialized database optimized for storing and searching through vectors (embeddings).

**Analogy:**  
Like a search engine index, but instead of indexing keywords, it indexes meaning. It's like having a library where books are organized by topic similarity, not alphabetically.

**How it works:**
```
1. Store: Each document chunk → embedding → stored in vector DB
2. Search: Query → embedding → find nearest neighbors
3. Return: Most similar chunks (by meaning, not keywords)
```

**In this project:**
- **Technology:** Chroma DB
- **Storage:** Persisted to disk at `./chroma_db/`
- **Collection:** Named "biology" (can have multiple collections)
- **Search method:** Cosine similarity (measures angle between vectors)

**Why Chroma?**
- Lightweight and easy to use
- Persists to disk (survives restarts)
- Fast similarity search
- Good for small to medium datasets

---

### 3. Semantic Search

**What is it?**  
Searching by **meaning** rather than exact keyword matching.

**Traditional Search (Keyword-based):**
```
Query: "plant energy process"
Matches: Documents containing "plant", "energy", "process"
Misses: Document saying "photosynthesis" (no keyword match)
```

**Semantic Search:**
```
Query: "plant energy process"
Matches: Documents about "photosynthesis", "chlorophyll", "glucose production"
Reason: Embeddings capture that these concepts are related
```

**In this project:**
- Uses embeddings to find semantically similar chunks
- Combined with BM25 (keyword search) for hybrid retrieval
- More accurate than keyword-only search

---

### 4. K Value (Top-K)

**What is it?**  
The number of most relevant results to retrieve from the database.

**Analogy:**  
Like asking Google to show you the "top 5" results instead of all 10,000 matches.

**In this project:**
- **Default K:** 6 chunks
- **Why 6?** Balance between:
  - Too few (K=2): Might miss important context
  - Too many (K=20): Noise, slower, more expensive
- **Configurable:** Set via `top_k` parameter in `RAGService`

**Trade-offs:**
- Higher K = More context, but slower and potentially less focused
- Lower K = Faster, but might miss relevant information

---

### 5. Chunking

**What is it?**  
Breaking large documents into smaller, manageable pieces.

**Why?**
- LLMs have token limits (can't process entire books at once)
- Better retrieval (find specific relevant sections)
- More precise context injection

**In this project:**
- **Chunk size:** 900 characters
- **Overlap:** 150 characters between chunks
- **Why overlap?** Prevents losing context at chunk boundaries

**Example:**
```
Document: "Photosynthesis is the process... [2000 characters]"

Chunk 1: characters 0-900
Chunk 2: characters 750-1650  (overlaps with chunk 1)
Chunk 3: characters 1500-2400 (overlaps with chunk 2)
```

---

### 6. BM25 (Lexical Search)

**What is it?**  
A keyword-based search algorithm (like what Google uses for text search).

**How it differs from semantic search:**
- **BM25:** Matches exact words and phrases
- **Semantic:** Matches meaning (even with different words)

**In this project:**
- Used alongside vector search (hybrid retrieval)
- Catches exact term matches that semantic search might miss
- Example: Query "DNA" → BM25 finds documents with "DNA", semantic finds "genetic material"

---

### 7. Reranking

**What is it?**  
Reordering retrieved results to put the most relevant ones first.

**Why needed?**
- Initial retrieval might not be perfectly ordered
- LLM can understand context better than simple similarity scores
- Improves final answer quality

**In this project:**
- Uses Gemini 2.5 Flash to rerank chunks
- Prompt: "Rank these chunks by relevance to the question"
- Returns reordered list of chunks

---

## What is RAG?

**RAG = Retrieval-Augmented Generation**

**The Problem RAG Solves:**
- LLMs have knowledge cutoff dates (don't know recent info)
- LLMs can hallucinate (make up facts)
- LLMs don't know your specific documents

**The RAG Solution:**
1. **Retrieve** relevant information from your documents
2. **Augment** the LLM prompt with that context
3. **Generate** an answer based on the retrieved context

**Simple Flow:**
```
User Question → Find Relevant Docs → Add to Prompt → LLM Answers
```

**Benefits:**
- ✅ Answers grounded in your documents (less hallucination)
- ✅ Can use up-to-date information
- ✅ Domain-specific knowledge (e.g., Khmer biology curriculum)
- ✅ Traceable sources (can cite which chunks were used)

---

## System Architecture

### High-Level Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    User Application                          │
│              (Frontend, Mobile App, etc.)                    │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP POST /ask
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    FastAPI Server                            │
│                    (src/main.py)                            │
│  • Endpoint: POST /ask                                       │
│  • Authentication: X-API-Key                                │
│  • Streaming Response                                        │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│                    RAG Service                              │
│                  (src/rag_service.py)                       │
│  • Hybrid Retrieval (Vector + BM25)                         │
│  • Reranking                                                │
│  • Prompt Assembly                                           │
│  • Answer Generation                                         │
└────────────────────────┬────────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         ▼               ▼               ▼
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  Chroma DB   │  │  BM25 Index  │  │  Gemini API  │
│ (Vector DB)  │  │ (In-Memory)  │  │  (LLM)       │
└──────────────┘  └──────────────┘  └──────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────┐
│                    Document Storage                         │
│                    (src/docs/*.txt)                         │
│  • biology.txt (Khmer biology content)                      │
│  • Other subject files                                      │
└─────────────────────────────────────────────────────────────┘
```

### Component Breakdown

| Component | Technology | Purpose |
|-----------|------------|---------|
| **API Layer** | FastAPI | REST endpoint, request handling |
| **RAG Service** | Custom Python class | Orchestrates retrieval and generation |
| **Vector Store** | Chroma DB | Stores and searches embeddings |
| **Embedding Model** | sentence-transformers/all-MiniLM-L6-v2 | Converts text to vectors |
| **Lexical Search** | BM25 | Keyword-based retrieval |
| **LLM** | Gemini 2.5 Flash | Reranking and answer generation |
| **Documents** | Text files | Source knowledge base |

---

## Complete Flow Explanation

### Phase 1: Startup & Indexing

**When:** Server starts up (one-time setup)

**What happens:**

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Server Starts (main.py startup_event)                    │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. RAGService Initialization                                │
│    • Load embedding model (all-MiniLM-L6-v2)                │
│    • Initialize text splitter (900 chars, 150 overlap)     │
│    • Set top_k = 6                                          │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Load Documents (load_documents_from_folder)              │
│    • Scan src/docs/ for *.txt files                         │
│    • Use LangChain TextLoader                               │
│    • Create Document objects with metadata                   │
│    • Add hash IDs for deduplication                          │
│                                                              │
│    Example: biology.txt → Document objects                  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Chunking (create_vector_store)                           │
│    • Split documents into 900-char chunks                   │
│    • 150-char overlap between chunks                        │
│    • Preserve metadata (source file, hash)                  │
│                                                              │
│    Example: 2348 lines → ~50 chunks                         │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Embedding Generation                                     │
│    • For each chunk:                                        │
│      Text → Embedding Model → Vector (384 numbers)         │
│    • Happens automatically when storing in Chroma            │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. Vector Store Creation                                    │
│    • Store chunks + embeddings in Chroma DB                 │
│    • Persist to ./chroma_db/ (survives restarts)            │
│    • Collection name: "biology"                             │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 7. BM25 Index Creation                                      │
│    • Tokenize all chunks (split by words)                  │
│    • Build BM25Okapi index for keyword search               │
│    • Stored in memory (not persisted)                       │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 8. Ready State                                              │
│    • Vector store: Ready                                    │
│    • BM25 index: Ready                                      │
│    • Server: Ready to accept requests                       │
└─────────────────────────────────────────────────────────────┘
```

**Key Points:**
- This happens **once** at startup
- Documents are processed and indexed
- Embeddings are computed and stored
- Takes time on first run (model loading, embedding generation)

---

### Phase 2: Query Processing

**When:** User sends POST request to `/ask`

**What happens:**

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Request Arrives                                           │
│    POST /ask                                                 │
│    Headers: X-API-Key: <key>                                │
│    Body: {"prompt": "តើស៊ីមណូស្ពែមជាអ្វី?"}              │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Authentication & Validation                              │
│    • Check X-API-Key matches INTERNAL_API_KEY               │
│    • Validate prompt is not empty                            │
│    • Check RAG service is initialized                       │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Hybrid Retrieval (hybrid_retrieve_async)                │
│                                                              │
│    ┌──────────────────┐      ┌──────────────────┐           │
│    │ Vector Search    │      │ BM25 Search      │           │
│    │ (Semantic)       │      │ (Keyword)        │           │
│    └────────┬─────────┘      └────────┬─────────┘           │
│             │                          │                     │
│             │ Query → Embedding        │ Query → Keywords    │
│             │ Find top 6 similar       │ Find top 6 matches  │
│             │                          │                     │
│             └──────────┬───────────────┘                     │
│                        │                                     │
│                        ▼                                     │
│              Merge & Deduplicate (by hash)                  │
│              Take top 6 unique chunks                        │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Reranking (rerank_async)                                │
│    • Send chunks + query to Gemini                          │
│    • Prompt: "Rank these chunks by relevance"               │
│    • Get ordered list of indices                            │
│    • Reorder chunks based on LLM ranking                     │
│                                                              │
│    Why? Initial retrieval might not be perfectly ordered    │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Memory Context (summarize_memory)                       │
│    • Currently returns empty (Redis disabled)               │
│    • Would contain previous Q&A pairs if enabled            │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. Prompt Assembly                                          │
│                                                              │
│    Prompt Template:                                         │
│    ┌────────────────────────────────────────────┐          │
│    │ Use ONLY the context and memory to answer.  │          │
│    │ If missing, reply: "អធ្យាស្រ័យ..."        │          │
│    │                                              │          │
│    │ MEMORY:                                      │          │
│    │ ---                                          │          │
│    │ {memory_text}                                │          │
│    │ ---                                          │          │
│    │                                              │          │
│    │ CONTEXT:                                     │          │
│    │ ---                                          │          │
│    │ {chunk 1 content}                            │          │
│    │ ---                                          │          │
│    │ {chunk 2 content}                            │          │
│    │ ... (up to 6 chunks)                         │          │
│    │ ---                                          │          │
│    │                                              │          │
│    │ QUESTION:                                    │          │
│    │ {user_prompt}                                │          │
│    └────────────────────────────────────────────┘          │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 7. Answer Generation                                        │
│    • Send prompt to Gemini 2.5 Flash                        │
│    • Model generates answer based on context                 │
│    • Extract response.text                                  │
│    • Fallback: "អធ្យាស្រ័យខ្ញុំមិនអាចជួយបានទេ"        │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 8. Memory Update (update_memory)                           │
│    • Currently no-op (Redis disabled)                       │
│    • Would store Q&A pair for future context               │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────┐
│ 9. Stream Response                                          │
│    • Return answer as streaming text                        │
│    • Currently returns full answer in one chunk              │
│    • (Future: token-by-token streaming)                     │
└─────────────────────────────────────────────────────────────┘
```

**Key Points:**
- **Hybrid retrieval** combines semantic (vector) and keyword (BM25) search
- **Reranking** improves result order using LLM understanding
- **Prompt** instructs model to answer ONLY from context
- **Fallback message** in Khmer if context is missing

---

## Technical Implementation Details

### Embedding Model Choice

**Model:** `sentence-transformers/all-MiniLM-L6-v2`

**Why this model?**
- ✅ **Fast:** Small model (80MB), quick inference
- ✅ **Multilingual:** Works reasonably well with Khmer (though not perfect)
- ✅ **Balanced:** Good trade-off between speed and quality
- ✅ **384 dimensions:** Efficient storage and search

**Limitations:**
- Not specifically trained on Khmer
- May not capture Khmer language nuances as well as English
- Consider Khmer-specific models for better performance

**Alternatives to consider:**
- `paraphrase-multilingual-MiniLM-L12-v2` (better multilingual, slower)
- Khmer-specific embedding models (if available)
- OpenAI embeddings (paid, but very good)

---

### Vector Database: Chroma

**Why Chroma?**
- ✅ **Simple:** Easy to use, minimal setup
- ✅ **Persistent:** Saves to disk, survives restarts
- ✅ **Fast:** Efficient similarity search
- ✅ **Lightweight:** No separate server needed

**Storage:**
- Location: `./chroma_db/`
- Format: SQLite + embeddings
- Collection: "biology" (can have multiple)

**How it works:**
```python
# Store
Chroma.from_documents(
    chunks,
    embedding=embeddings,
    collection_name="biology",
    persist_directory="./chroma_db"
)

# Search
retriever = vector_store.as_retriever(search_kwargs={"k": 6})
results = retriever.invoke(query)
```

---

### Hybrid Retrieval Strategy

**Why hybrid?**
- **Vector search** catches semantic similarity (meaning)
- **BM25** catches exact keyword matches
- **Combined** = better coverage

**How it works:**
```python
# 1. Vector search (semantic)
vector_docs = retriever.invoke(query)  # Top 6 by meaning

# 2. BM25 search (keyword)
bm25_docs = bm25.get_top_n(query.split(), chunks, n=6)  # Top 6 by keywords

# 3. Merge and deduplicate
combined = {doc.id_hash: doc for doc in vector_docs + bm25_docs}
final = list(combined.values())[:6]  # Top 6 unique
```

**Benefits:**
- Catches both "photosynthesis" (semantic) and "DNA" (exact match)
- Reduces misses from either method alone
- Better recall (finds more relevant chunks)

---

### Reranking with LLM

**Why rerank?**
- Initial retrieval scores might not reflect true relevance
- LLM understands context better than similarity scores
- Improves final answer quality

**How it works:**
```python
prompt = """
Rank the following document chunks by relevance to the question.
Return only the ordered list of indexes (0-based).

QUESTION: {query}

CHUNKS:
0: {chunk 1}
---
1: {chunk 2}
---
...
"""

response = model.generate_content(prompt)
ranked_indexes = extract_numbers(response.text)
ranked_docs = [docs[i] for i in ranked_indexes]
```

**Trade-offs:**
- ✅ Better ordering
- ❌ Slower (extra LLM call)
- ❌ More expensive (uses API quota)

**Alternatives:**
- Skip reranking (faster, cheaper)
- Use specialized reranker (Cohere, Jina)
- Use simpler scoring (cosine similarity + BM25 score)

---

### Chunking Strategy

**Parameters:**
- **Chunk size:** 900 characters
- **Overlap:** 150 characters
- **Splitter:** RecursiveCharacterTextSplitter

**Why these values?**
- **900 chars:** Fits ~200-300 tokens (good for context window)
- **150 overlap:** Prevents losing context at boundaries
- **Recursive:** Tries to split at sentence/paragraph boundaries first

**Example:**
```
Document: "Photosynthesis is... [2000 chars]"

Chunk 1: [0-900]
Chunk 2: [750-1650]  ← overlaps 150 chars with chunk 1
Chunk 3: [1500-2400] ← overlaps 150 chars with chunk 2
```

**Considerations:**
- Too small: Loses context, more chunks to search
- Too large: Less precise retrieval, might hit token limits
- No overlap: Context lost at boundaries

---

## Use Cases & Examples

### Use Case 1: Biology Question in Khmer

**Query:** "តើស៊ីមណូស្ពែមជាអ្វី?" (What is a synapse?)

**Flow:**
1. Query converted to embedding
2. Vector search finds chunks about "synapse", "neurons", "nerve cells"
3. BM25 finds chunks containing "ស៊ីមណូស្ពែម"
4. Hybrid retrieval merges results
5. Reranking prioritizes most relevant chunks
6. Gemini generates answer in Khmer based on retrieved context

**Expected Response:**
- Answer in Khmer explaining synapses
- Grounded in biology.txt content
- Uses terminology from the curriculum

**Accuracy:**
- ✅ High if biology.txt contains synapse information
- ❌ Falls back to "អធ្យាស្រ័យ..." if not found

---

### Use Case 2: Conceptual Question

**Query:** "តើរុក្ខជាតិធ្វើចំណីដោយរបៀបណា?" (How do plants make food?)

**Flow:**
1. Semantic search finds chunks about "photosynthesis", "chlorophyll", "glucose"
2. BM25 might find "រុក្ខជាតិ" (plants) if present
3. Reranking ensures photosynthesis chunks are prioritized
4. Answer explains photosynthesis process

**Why this works:**
- Semantic search finds "photosynthesis" even if query doesn't use that word
- Captures meaning, not just keywords

---

### Use Case 3: Specific Detail Question

**Query:** "តើ DNA មានប៉ុន្មានប្រភេទ?" (How many types of DNA?)

**Flow:**
1. BM25 finds exact "DNA" matches
2. Vector search finds related genetic material chunks
3. Hybrid retrieval combines both
4. Answer provides specific count from documents

**Accuracy:**
- ✅ Very accurate if document contains exact information
- ✅ Cites specific numbers from curriculum
- ❌ Won't make up numbers if not in documents

---

### Use Case 4: Out-of-Scope Question

**Query:** "តើអាចញ៉ាំបាយបានទេ?" (Can I eat rice?)

**Flow:**
1. Retrieval finds no relevant biology chunks
2. Context is empty or irrelevant
3. Prompt instructs model to say "អធ្យាស្រ័យខ្ញុំមិនអាចជួយបានទេ"

**Expected Response:**
- Fallback message (not biology-related)
- Model doesn't hallucinate an answer
- Stays grounded in documents

---

### Use Case 5: Multi-Part Question

**Query:** "ពន្យល់អំពីការបំបែកកោសិកា" (Explain cell division)

**Flow:**
1. Retrieval finds multiple chunks about cell division
2. Reranking orders them logically (mitosis, meiosis, etc.)
3. Answer synthesizes information from multiple chunks
4. Provides comprehensive explanation

**Accuracy:**
- ✅ Combines information from multiple sources
- ✅ More complete answer than single chunk
- ⚠️ Model synthesizes (some interpretation)

---

## Accuracy vs. Freedom

### How Strict is the System?

**Current Implementation:**
- **Prompt instructs:** "Use ONLY the context and memory to answer"
- **Fallback:** Returns Khmer message if context missing
- **No grounding:** Model can still interpret and synthesize

**What this means:**

| Scenario | Behavior | Accuracy |
|----------|----------|----------|
| **Exact match in docs** | Cites specific information | ✅ Very high |
| **Related info in docs** | Synthesizes from context | ✅ High (with interpretation) |
| **Partial info** | Fills gaps with model knowledge | ⚠️ Medium (may hallucinate) |
| **No relevant info** | Returns fallback message | ✅ High (doesn't make up) |

### Examples

**Strict (High Accuracy):**
```
Query: "តើ DNA មានប៉ុន្មានប្រភេទ?"
Document: "DNA has 2 types: A-DNA and B-DNA"
Answer: "DNA has 2 types: A-DNA and B-DNA" ✅ Exact
```

**Synthesized (Medium Accuracy):**
```
Query: "ពន្យល់អំពីការបំបែកកោសិកា"
Document: Multiple chunks about mitosis and meiosis
Answer: Combines information, adds transitions ⚠️ Interpreted
```

**Hallucination Risk:**
```
Query: "តើកោសិកាមានពណ៌អ្វី?"
Document: No color information
Answer: Might say "transparent" (model knowledge) ⚠️ Not in docs
```

### Improving Accuracy

**Current safeguards:**
- ✅ "Use ONLY context" instruction
- ✅ Fallback message if missing
- ✅ Hybrid retrieval (better context)

**Potential improvements:**
- Add source citations (which chunks were used)
- Stricter prompt (reject if not in context)
- Confidence scores (low confidence → fallback)
- Fact-checking layer

---

## Future Work & Improvements

### 1. Redis Memory System

**Current State:** Disabled (commented out in code)

**Why Redis?**
- **Persistent memory:** Store conversation history across requests
- **Fast access:** In-memory database, very quick lookups
- **Scalable:** Can handle multiple users/sessions
- **Structured storage:** Easy to manage Q&A pairs

**How it would work:**
```python
# Store conversation
await redis.set("user:123:memory", json.dumps([
    {"Q": "What is DNA?", "A": "DNA is..."},
    {"Q": "How many types?", "A": "There are 2 types..."}
]))

# Retrieve for context
memory = await redis.get("user:123:memory")
# Add to prompt for better context
```

**Benefits:**
- ✅ Follow-up questions work better ("What about RNA?")
- ✅ Maintains conversation context
- ✅ Personalized responses

**Implementation:**
- Re-enable Redis connection
- Store Q&A pairs per user/session
- Add memory to prompt context
- Implement memory summarization (token limits)

---

### 2. Token-Level Streaming

**Current State:** Returns full answer in one chunk

**Why streaming?**
- Better user experience (see answer as it generates)
- Lower perceived latency
- Can cancel if wrong

**How to implement:**
```python
# Current (non-streaming)
response = model.generate_content(prompt)
yield response.text

# Future (streaming)
for chunk in model.generate_content_stream(prompt):
    yield chunk.text
```

**Challenges:**
- Gemini API streaming support
- Error handling during stream
- Partial responses

---

### 3. Multi-Collection Support

**Current State:** Single "biology" collection

**Why multiple collections?**
- Different subjects (biology, chemistry, physics)
- Different languages
- Different document types

**How it would work:**
```python
# Current
rag_service = RAGService(collection_name="biology")

# Future
rag_service = RAGService()
rag_service.switch_collection("chemistry")
# Or
rag_service = RAGService(multi_collection=True)
results = rag_service.search(["biology", "chemistry"], query)
```

**Benefits:**
- ✅ Support multiple subjects
- ✅ Better organization
- ✅ Can search across collections

---

### 4. Better Embedding Models for Khmer

**Current:** `all-MiniLM-L6-v2` (multilingual but not Khmer-optimized)

**Alternatives:**
- Khmer-specific embedding models
- `paraphrase-multilingual-MiniLM-L12-v2` (better multilingual)
- Fine-tune on Khmer biology corpus

**Benefits:**
- ✅ Better semantic understanding of Khmer
- ✅ More accurate retrieval
- ✅ Better handling of Khmer terminology

---

### 5. Source Citations

**Current State:** No citation of which chunks were used

**Why citations?**
- Transparency (users know sources)
- Verifiability (can check original documents)
- Trust (shows grounding)

**How to implement:**
```python
# Add to response
{
    "answer": "DNA has 2 types...",
    "sources": [
        {"chunk": "...", "file": "biology.txt", "line": 123},
        {"chunk": "...", "file": "biology.txt", "line": 456}
    ]
}
```

---

### 6. Evaluation & Metrics

**What to measure:**
- Retrieval accuracy (are we finding right chunks?)
- Answer quality (is answer correct?)
- Latency (how fast?)
- Cost (API usage)

**How to implement:**
- Test dataset with Q&A pairs
- Automated evaluation scripts
- Human evaluation for quality
- Logging and monitoring

---

### 7. Additional Document Formats

**Current:** Only `.txt` files

**Future:**
- PDF documents
- Word documents (.docx)
- Markdown files
- Web scraping

**Implementation:**
```python
# Add loaders
from langchain_community.document_loaders import PyPDFLoader, Docx2txtLoader

loaders = {
    ".txt": TextLoader,
    ".pdf": PyPDFLoader,
    ".docx": Docx2txtLoader
}
```

---

### 8. Response Formatting

**Current:** Plain text response

**Future:**
- Support `responseType` parameter
- Markdown formatting
- Structured JSON (for complex answers)
- TopicContent_V3 format

**Implementation:**
```python
if response_type == "komplex":
    return format_as_topic_content(answer)
elif response_type == "markdown":
    return format_as_markdown(answer)
```

---

### 9. Performance Optimizations

**Current bottlenecks:**
- Embedding generation (first time)
- Reranking (extra LLM call)
- Synchronous operations

**Improvements:**
- Cache embeddings
- Parallel retrieval (vector + BM25 simultaneously)
- Async operations throughout
- Batch processing

---

### 10. Security & Rate Limiting

**Current:** Basic API key authentication

**Future:**
- Rate limiting (prevent abuse)
- Per-user authentication
- Input sanitization
- Output filtering

---

## Summary

### Key Takeaways

1. **RAG combines retrieval + generation** for accurate, grounded answers
2. **Hybrid retrieval** (vector + BM25) finds better results
3. **Embeddings** convert text to searchable vectors
4. **Chunking** breaks documents into manageable pieces
5. **Reranking** improves result quality
6. **System is grounded** but allows some interpretation

### Current Strengths

- ✅ Hybrid retrieval (semantic + keyword)
- ✅ Persistent vector store
- ✅ Grounded answers (less hallucination)
- ✅ Khmer language support
- ✅ Streaming responses

### Areas for Improvement

- ⚠️ Redis memory (disabled)
- ⚠️ Token-level streaming (simulated)
- ⚠️ Khmer embedding model (could be better)
- ⚠️ Source citations (missing)
- ⚠️ Multi-collection support (single collection)

---

## Quick Reference

### Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `top_k` | 6 | Number of chunks to retrieve |
| `chunk_size` | 900 | Characters per chunk |
| `chunk_overlap` | 150 | Overlap between chunks |
| `embedding_model` | all-MiniLM-L6-v2 | Embedding model |
| `llm_model` | gemini-2.5-flash | LLM for reranking/generation |
| `collection_name` | "biology" | Chroma collection name |

### File Locations

- **Documents:** `src/docs/*.txt`
- **Vector DB:** `./chroma_db/`
- **RAG Service:** `src/rag_service.py`
- **API Endpoint:** `src/main.py` (POST /ask)

### Key Functions

- `load_documents_from_folder()` - Load and parse documents
- `create_vector_store()` - Chunk, embed, and index
- `hybrid_retrieve_async()` - Find relevant chunks
- `rerank_async()` - Reorder by relevance
- `ask_async()` - Full RAG pipeline
- `stream_answer_async()` - Streaming wrapper

---

*This guide explains the RAG implementation for developers with a software engineering background. For questions or improvements, refer to the codebase or documentation.*
