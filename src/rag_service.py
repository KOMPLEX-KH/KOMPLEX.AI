import os
import hashlib
import logging
import json
import re
import unicodedata
from pathlib import Path
from typing import List, Optional, AsyncGenerator
import asyncio
from concurrent.futures import ThreadPoolExecutor

import redis.asyncio as redis
import google.generativeai as genai
from fastapi import FastAPI, HTTPException, Request, Header
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from langchain_community.document_loaders import TextLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain.text_splitter import RecursiveCharacterTextSplitter
from rank_bm25 import BM25Okapi

try:
    from langchain_core.documents import Document
except ImportError:
    from langchain.schema import Document

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(levelname)s | %(message)s")

DEFAULT_MEMORY_KEY = "user_memory:default"


def _bm25_tokens(text: str) -> List[str]:
    """BM25 tokenization: whitespace + character 4-grams for long tokens (helps Khmer / copy-paste)."""
    if not text or not text.strip():
        return []
    tokens = re.split(r"\s+", text.strip())
    out = []
    for t in tokens:
        out.append(t)
        if len(t) >= 4:
            for i in range(len(t) - 3):
                out.append(t[i : i + 4])
    return out


# ================================================
# RAG Service
# ================================================
class RAGService:
    def __init__(
        self,
        persist_directory: str = "./chroma_db",
        collection_name: str = "biology",
        redis_url: str = "redis://localhost:6379",
        top_k: int = 10,
        memory_max: int = 10,
        memory_token_limit: int = 2000,
    ):
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.top_k = top_k
        self.memory_max = memory_max
        self.memory_token_limit = memory_token_limit

        # Embeddings + splitter
        self.embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
        self.text_splitter = RecursiveCharacterTextSplitter(chunk_size=900, chunk_overlap=150, add_start_index=True)

        # Gemini model
        self.model = None

        # Vector store + BM25
        self.vector_store: Optional[Chroma] = None
        self.retriever = None
        self.bm25: Optional[BM25Okapi] = None
        self.docs: List[Document] = []
        self.chunks: List[Document] = []

        # Redis
        self.redis_url = redis_url
        self.redis: Optional[redis.Redis] = None

        # ThreadPool
        self.executor = ThreadPoolExecutor(max_workers=4)

    # -------------------------------
    # Redis memory
    # -------------------------------
    async def init_redis(self):
        # Temporarily disabled Redis usage.
        # if self.redis is None:
        #     self.redis = await redis.from_url(self.redis_url, encoding="utf-8", decode_responses=True)
        #     logging.info("Redis initialized for chat memory.")
        return

    async def update_memory(self, query: str, answer: str):
        # Temporarily disabled Redis usage.
        # await self.init_redis()
        # mem_json = await self.redis.get(DEFAULT_MEMORY_KEY)
        # memory_list = json.loads(mem_json) if mem_json else []
        # memory_list.append(f"Q: {query}\nA: {answer}")
        # memory_list = memory_list[-self.memory_max:]
        # await self.redis.set(DEFAULT_MEMORY_KEY, json.dumps(memory_list))
        return

    async def get_memory_context(self) -> str:
        # Temporarily disabled Redis usage.
        # await self.init_redis()
        # mem_json = await self.redis.get(DEFAULT_MEMORY_KEY)
        # memory_list = json.loads(mem_json) if mem_json else []
        # return "\n".join(memory_list)
        return ""

    async def summarize_memory(self) -> str:
        # Temporarily disabled Redis-backed memory summarization.
        # memory = await self.get_memory_context()
        # if len(memory) <= self.memory_token_limit:
        #     return memory
        # return memory[-self.memory_token_limit:]
        return ""


    # -------------------------------
    # Gemini model
    # -------------------------------
    def init_model(self):
        if self.model:
            return
        api_key = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        if not api_key:
            raise RuntimeError("GEMINI_API_KEY not set")
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel("gemini-2.5-flash")
        logging.info("Gemini 2.5 Flash model initialized.")

    # -------------------------------
    # Document loading
    # -------------------------------
    def _hash_text(self, text: str) -> str:
        return hashlib.md5(text.encode()).hexdigest()

    def load_documents_from_folder(self, folder: str, pattern: str = "*.txt") -> List[Document]:
        folder_path = Path(folder)
        if not folder_path.exists():
            raise FileNotFoundError(f"Folder not found: {folder}")

        all_docs = []
        for file in sorted(folder_path.glob(pattern)):
            try:
                loader = TextLoader(str(file), encoding="utf-8")
                docs = loader.load()
                for d in docs:
                    d.metadata["source"] = str(file)
                    d.metadata["id_hash"] = self._hash_text(d.page_content)
                all_docs.extend(docs)
            except Exception as e:
                logging.warning("Skipping file %s: %s", file, e)
                continue

        self.docs = all_docs
        logging.info("Loaded %s documents from %s", len(all_docs), folder)
        return all_docs

    # -------------------------------
    # Vector store + BM25
    # -------------------------------
    def create_vector_store(self):
        if not self.docs:
            logging.warning("create_vector_store called with no documents; retriever will return nothing.")
            return
        try:
            logging.info("Splitting documents into chunks...")
            self.chunks = self.text_splitter.split_documents(self.docs)
            for c in self.chunks:
                c.metadata["id_hash"] = self._hash_text(c.page_content)

            logging.info("Creating Chroma vector store with %s chunks at %s...", len(self.chunks), self.persist_directory)
            vector_store = Chroma.from_documents(
                self.chunks,
                embedding=self.embeddings,
                collection_name=self.collection_name,
                persist_directory=self.persist_directory,
            )
            self.vector_store = vector_store
            self.retriever = vector_store.as_retriever(search_kwargs={"k": self.top_k})

            logging.info("Building BM25 index...")
            tokenized = [_bm25_tokens(chunk.page_content) for chunk in self.chunks]
            self.bm25 = BM25Okapi(tokenized)
            logging.info("RAG index ready: %s chunks, retriever and BM25 built.", len(self.chunks))
        except Exception as e:
            logging.exception("create_vector_store failed: %s", e)
            self.vector_store = None
            self.retriever = None
            self.bm25 = None
            raise

    # -------------------------------
    # Hybrid retrieval
    # -------------------------------
    @staticmethod
    def _normalize_query(text: str) -> str:
        """Normalize query for consistent matching (Unicode NFC, collapse whitespace)."""
        if not text:
            return text
        normalized = unicodedata.normalize("NFC", text.strip())
        return " ".join(normalized.split())

    def _hybrid_retrieve(self, query: str, top_k: Optional[int] = None) -> List[Document]:
        top_k = top_k or self.top_k
        query = self._normalize_query(query)
        # NOTE: Don't call private `_get_relevant_documents()` directly; newer LangChain
        # versions require an internal `run_manager` kwarg which breaks this call.
        if self.retriever:
            try:
                # Preferred public API in newer LangChain (retrievers are Runnables)
                vector_docs = self.retriever.invoke(query)
            except Exception:
                # Backwards-compat for older retriever interface
                vector_docs = self.retriever.get_relevant_documents(query)
        else:
            vector_docs = []
        query_tokens = _bm25_tokens(query)
        bm25_docs = self.bm25.get_top_n(query_tokens, self.chunks, n=top_k) if (self.bm25 and query_tokens) else []
        # Prefer BM25 results first (reliable for Khmer/copy-paste); embedding model is English-only
        bm25_ids = {d.metadata["id_hash"] for d in bm25_docs}
        vector_only = [d for d in vector_docs if d.metadata["id_hash"] not in bm25_ids]
        merged = list(bm25_docs) + vector_only
        return merged[:top_k]

    async def hybrid_retrieve_async(self, query: str, top_k: Optional[int] = None):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, self._hybrid_retrieve, query, top_k)

    # -------------------------------
    # Rerank
    # -------------------------------
    def rerank_blocking(self, query: str, docs: List[Document]) -> List[Document]:
        if not docs:
            return docs
        self.init_model()
        if self.model is None:
            return docs
        prompt = "Rank the following document chunks by relevance to the question. Return only the ordered list of indexes (0-based), e.g. 2,0,1,3,4,5.\n\n"
        prompt += f"QUESTION: {query}\n\nCHUNKS:\n"
        for i, d in enumerate(docs):
            prompt += f"{i}: {d.page_content}\n---\n"
        try:
            response = self.model.generate_content(prompt)
            raw_indexes = [int(i) for i in re.findall(r"\d+", response.text)]
            # Use model order for mentioned indexes, then append any missing so we never drop chunks
            seen = set()
            ordered = []
            for i in raw_indexes:
                if 0 <= i < len(docs) and i not in seen:
                    seen.add(i)
                    ordered.append(i)
            for i in range(len(docs)):
                if i not in seen:
                    ordered.append(i)
            return [docs[i] for i in ordered]
        except Exception:
            return docs


    async def rerank_async(self, query: str, docs: List[Document]) -> List[Document]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, self.rerank_blocking, query, docs)

    # -------------------------------
    # Ask
    # -------------------------------
    async def ask_async(self, query: str):
        retrieved_docs = await self.hybrid_retrieve_async(query)
        if not retrieved_docs and query:
            # Fallback: try with start of query (e.g. first sentence) to still get some context
            short = " ".join(query.split()[:15]).strip() or query[:80]
            if short != query:
                retrieved_docs = await self.hybrid_retrieve_async(short, top_k=self.top_k)
                if retrieved_docs:
                    logging.info("Retrieval fallback (short query) returned %s docs", len(retrieved_docs))
        if not retrieved_docs:
            logging.warning("Retriever returned 0 documents for query: %s", query[:80])
        ranked_docs = await self.rerank_async(query, retrieved_docs)
        memory_text = await self.summarize_memory()
        context_text = "\n\n---\n\n".join([d.page_content for d in ranked_docs])

        self.init_model()
        prompt = f"""You are answering from a biology textbook. The CONTEXT below contains question-answer pairs. Often a question is followed by "ចម្លើយ:" and then the answer.

Your task: If the QUESTION (from the user) is the same or very similar to a question in the CONTEXT, reply with the answer that comes after "ចម្លើយ:" for that question. Use the exact wording from CONTEXT when possible. Reply in Khmer.

Only if the QUESTION cannot be answered from the CONTEXT at all, reply exactly: "អធ្យាស្រ័យខ្ញុំមិនអាចជួយបានទេ"

MEMORY:
---
{memory_text}
---

CONTEXT:
---
{context_text}
---

QUESTION:
{query}
"""
        fallback = "អធ្យាស្រ័យខ្ញុំមិនអាចជួយបានទេ"
        model = self.model
        if model is None:
            await self.update_memory(query, fallback)
            return fallback, ranked_docs
        loop = asyncio.get_running_loop()
        try:
            response = await loop.run_in_executor(self.executor, model.generate_content, prompt)
            answer = (response.text or "").strip()
            if not answer:
                logging.warning("Gemini returned empty response for query: %s", query[:80])
                answer = fallback
        except Exception as e:
            logging.exception("Gemini generate_content failed for query %s: %s", query[:80], e)
            answer = fallback

        await self.update_memory(query, answer)
        return answer, ranked_docs

    # -------------------------------
    # Stream
    # -------------------------------
    async def stream_answer_async(self, query: str) -> AsyncGenerator[str, None]:
        """
        Simple streaming wrapper around `ask_async`.

        Note:
        - The previous implementation used `self.model.stream_generate(...)`, which
          is not a valid Google Generative AI Python client method and was raising
          an exception on every call.
        - That exception was caught and the fallback text
          "អធ្យាស្រ័យខ្ញុំមិនអាចជួយបានទេ" was always returned, even when the
          answer existed in the documents.
        - We now delegate to `ask_async` (which uses the correct `generate_content`
          API) and stream the full answer as a single chunk.
        """
        try:
            answer, _ = await self.ask_async(query)
            yield answer
        except Exception:
            # If anything goes wrong, keep the same safe fallback message.
            yield "អធ្យាស្រ័យខ្ញុំមិនអាចជួយបានទេ"

