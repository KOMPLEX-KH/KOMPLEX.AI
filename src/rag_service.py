import os
import hashlib
import logging
import json
import re
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

# ================================================
# RAG Service
# ================================================
class RAGService:
    def __init__(
        self,
        persist_directory: str = "./chroma_db",
        collection_name: str = "biology",
        redis_url: str = "redis://localhost:6379",
        top_k: int = 6,
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
        for file in folder_path.glob(pattern):
            loader = TextLoader(str(file), encoding="utf-8")
            docs = loader.load()
            for d in docs:
                d.metadata["source"] = str(file)
                d.metadata["id_hash"] = self._hash_text(d.page_content)
            all_docs.extend(docs)

        self.docs = all_docs
        logging.info(f"Loaded {len(all_docs)} documents from {folder}")
        return all_docs

    # -------------------------------
    # Vector store + BM25
    # -------------------------------
    def create_vector_store(self):
        logging.info("Splitting documents into chunks...")
        self.chunks = self.text_splitter.split_documents(self.docs)
        for c in self.chunks:
            c.metadata["id_hash"] = self._hash_text(c.page_content)

        logging.info(f"Creating Chroma vector store with {len(self.chunks)} chunks...")
        self.vector_store = Chroma.from_documents(
            self.chunks,
            embedding=self.embeddings,
            collection_name=self.collection_name,
            persist_directory=self.persist_directory
        )
        self.retriever = self.vector_store.as_retriever(search_kwargs={"k": self.top_k})

        tokenized = [chunk.page_content.split() for chunk in self.chunks]
        self.bm25 = BM25Okapi(tokenized)
        logging.info("BM25 index built on chunks.")

    # -------------------------------
    # Hybrid retrieval
    # -------------------------------
    def _hybrid_retrieve(self, query: str, top_k: Optional[int] = None) -> List[Document]:
        top_k = top_k or self.top_k
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
        bm25_docs = self.bm25.get_top_n(query.split(), self.chunks, n=top_k) if self.bm25 else []
        combined = {d.metadata["id_hash"]: d for d in vector_docs + bm25_docs}
        return list(combined.values())[:top_k]

    async def hybrid_retrieve_async(self, query: str, top_k: Optional[int] = None):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(self.executor, self._hybrid_retrieve, query, top_k)

    # -------------------------------
    # Rerank
    # -------------------------------
    def rerank_blocking(self, query: str, docs: List[Document]) -> List[Document]:
        self.init_model()
        prompt = "Rank the following document chunks by relevance to the question. Return only the ordered list of indexes (0-based).\n\n"
        prompt += f"QUESTION: {query}\n\nCHUNKS:\n"
        for i, d in enumerate(docs):
            prompt += f"{i}: {d.page_content}\n---\n"
        try:
            response = self.model.generate_content(prompt)
            ranked_indexes = [int(i) for i in re.findall(r"\d+", response.text)]
            ranked_docs = [docs[i] for i in ranked_indexes if i < len(docs)]
            return ranked_docs if ranked_docs else docs
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
        ranked_docs = await self.rerank_async(query, retrieved_docs)
        memory_text = await self.summarize_memory()
        context_text = "\n\n---\n\n".join([d.page_content for d in ranked_docs])

        self.init_model()
        prompt = f"""
Use ONLY the context and memory to answer.
    If missing, reply: "អធ្យាស្រ័យខ្ញុំមិនអាចជួយបានទេ"

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
        loop = asyncio.get_running_loop()
        try:
            response = await loop.run_in_executor(self.executor, self.model.generate_content, prompt)
            answer = response.text.strip()
        except Exception:
            answer = "អធ្យាស្រ័យខ្ញុំមិនអាចជួយបានទេ"

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

