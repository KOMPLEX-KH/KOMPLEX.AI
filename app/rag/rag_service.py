import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Any, List, Optional
import asyncio
from concurrent.futures import ThreadPoolExecutor
from app.core.gemini import client
from app.instructions.general_preprompt import general_pre_prompt
from app.models.reponse_type import ResponseType
from langchain_community.document_loaders import TextLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_text_splitters import RecursiveCharacterTextSplitter
from rank_bm25 import BM25Okapi
from langchain_core.documents import Document

logger = logging.getLogger("complex.rag")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

# One Chroma collection for all subjects: retrieval is query-only, no per-subject routing.
DEFAULT_CHROMA_PERSIST_DIR = "./chroma_db"
DEFAULT_CHROMA_COLLECTION = "komplex_rag"


# ================================================
# RAG Service
# ================================================
class RAGService:
    """
    Single-vector-store RAG: all documents under `app/docs` are chunked, embedded,
    and stored in one Chroma collection (`DEFAULT_CHROMA_COLLECTION`). Hybrid search
    (dense + BM25) runs over that pool—no subject/collection selection at query time.
    """

    def __init__(
        self,
        persist_directory: str = DEFAULT_CHROMA_PERSIST_DIR,
        collection_name: str = DEFAULT_CHROMA_COLLECTION,
        top_k: int = 10,
    ):
        self.persist_directory = persist_directory
        self.collection_name = collection_name
        self.top_k = top_k

        # Embeddings + splitter
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=900, chunk_overlap=150, add_start_index=True
        )

        # Vector store + BM25
        self.vector_store: Optional[Chroma] = None
        # Retriever type varies by LangChain version; use Any for invoke vs legacy API.
        self.retriever: Any = None
        self.bm25: Optional[BM25Okapi] = None
        self.docs: List[Document] = []
        self.chunks: List[Document] = []

        # ThreadPool
        self.executor = ThreadPoolExecutor(max_workers=4)

    # -------------------------------
    # Document loading
    # -------------------------------
    def _hash_text(self, text: str) -> str:
        return hashlib.md5(text.encode()).hexdigest()

    def load_documents_from_folder(
        self, folder: str, pattern: str = "*.txt"
    ) -> List[Document]:
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
        logger.info("Loaded documents=%d from %s", len(all_docs), folder)
        return all_docs

    # -------------------------------
    # Vector store + BM25
    # -------------------------------
    def create_vector_store(self):
        logger.info("Splitting documents into chunks...")
        self.chunks = self.text_splitter.split_documents(self.docs)
        for c in self.chunks:
            c.metadata["id_hash"] = self._hash_text(c.page_content)

        logger.info(
            "Creating Chroma store: collection=%r persist=%r chunks=%s",
            self.collection_name,
            self.persist_directory,
            len(self.chunks),
        )
        self.vector_store = Chroma.from_documents(
            self.chunks,
            embedding=self.embeddings,
            collection_name=self.collection_name,
            persist_directory=self.persist_directory,
        )
        self.retriever = self.vector_store.as_retriever(search_kwargs={"k": self.top_k})

        tokenized = [chunk.page_content.split() for chunk in self.chunks]
        self.bm25 = BM25Okapi(tokenized)
        logger.info("BM25 index built on chunks.")

    # -------------------------------
    # Hybrid retrieval
    # -------------------------------
    def _hybrid_retrieve(
        self, query: str, top_k: Optional[int] = None
    ) -> List[Document]:
        top_k = top_k or self.top_k
        t0 = time.perf_counter()
        # NOTE: Don't call private `_get_relevant_documents()` directly; newer LangChain
        # versions require an internal `run_manager` kwarg which breaks this call.
        if self.retriever:
            try:
                # Preferred public API in newer LangChain (retrievers are Runnables)
                vector_docs = self.retriever.invoke(query)
            except Exception:
                # Older retrievers expose get_relevant_documents (not on all type stubs)
                legacy_get = getattr(self.retriever, "get_relevant_documents", None)
                vector_docs = (
                    legacy_get(query) if callable(legacy_get) else []
                )
        else:
            vector_docs = []
        vector_count = len(vector_docs)
        bm25_docs = (
            self.bm25.get_top_n(query.split(), self.chunks, n=top_k)
            if self.bm25
            else []
        )
        bm25_count = len(bm25_docs)

        combined = {d.metadata["id_hash"]: d for d in vector_docs + bm25_docs}
        merged_docs = list(combined.values())[:top_k]
        merged_count = len(combined)

        sources = [
            (d.metadata.get("source") if hasattr(d, "metadata") else None)
            for d in merged_docs[:3]
        ]
        ms = (time.perf_counter() - t0) * 1000
        logger.info(
            "[RAG/RETRIEVE] vector=%d bm25=%d merged=%d timeMs=%.1f sources=%s queryPreview=%r",
            vector_count,
            bm25_count,
            merged_count,
            ms,
            sources,
            query[:120],
        )
        return merged_docs

    async def hybrid_retrieve_async(self, query: str, top_k: Optional[int] = None):
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            self.executor, self._hybrid_retrieve, query, top_k
        )

    @staticmethod
    def _extract_candidate_json(raw: str) -> Optional[str]:
        text = (raw or "").strip()
        if not text:
            return None
        if text.startswith("[") and text.endswith("]"):
            return text
        match = re.search(r"\[[\s\S]*\]", text)
        return match.group(0) if match else None

    @staticmethod
    def _looks_like_json_artifact(text: str) -> bool:
        """
        Best-effort detector for model outputs that accidentally return JSON/code-fences
        when we asked for Markdown (responseType=NORMAL).
        """
        t = (text or "").strip()
        if not t:
            return False

        # Common failure mode: ```json ... ```
        if re.search(r"```\\s*json", t, flags=re.IGNORECASE):
            return True
        if t.startswith("```") and "json" in t[:50].lower():
            return True

        # Another failure mode: output starts with raw JSON
        if t.startswith("{") or t.startswith("["):
            lowered = t.lower()
            # TopicContent-ish keys
            jsonish_keys = ['"topic"', '"type"', '"props"', '"answer"', '"question"']
            return any(k in lowered for k in jsonish_keys)

        return False

    @staticmethod
    def _is_valid_topic_content(payload: Any) -> bool:
        if not isinstance(payload, list) or not payload:
            return False
        for item in payload:
            if not isinstance(item, dict):
                return False
            if "type" not in item or "props" not in item:
                return False
            if not isinstance(item["type"], str):
                return False
            if not isinstance(item["props"], dict):
                return False
        return True

    @staticmethod
    def _komplex_fallback_node(message: str) -> str:
        safe_payload = [
            {
                "type": "definition",
                "props": {
                    "title": "",
                    "content": [{"type": "text", "value": message}],
                },
            }
        ]
        return json.dumps(safe_payload, ensure_ascii=False)

    @staticmethod
    def _build_rag_context(docs: List[Document], max_context_chars: int = 6000) -> str:
        context_parts: List[str] = []
        total_chars = 0
        for i, d in enumerate(docs, start=1):
            part = (d.page_content or "").strip()
            if not part:
                continue
            source = d.metadata.get("source", "unknown") if hasattr(d, "metadata") else "unknown"
            labeled = f"[Chunk {i} | Source: {source}]\n{part}"
            if total_chars > 0 and total_chars + len(labeled) > max_context_chars:
                break
            context_parts.append(labeled)
            total_chars += len(labeled)
        return "\n\n---\n\n".join(context_parts)

    @staticmethod
    def _build_previous_context(
        rag_context: str,
        user_previous_context: Optional[str],
    ) -> str:
        grounding = (
            "RAG CONTEXT ខាងក្រោមគឺជាប្រភពព័ត៌មានសំខាន់បំផុតសម្រាប់ចម្លើយនេះ។ "
            "ប្រសិនបើមានព័ត៌មានពាក់ព័ន្ធក្នុង RAG CONTEXT ត្រូវប្រើវាជាមូលដ្ឋាន។ "
            "កុំបន្ថែមព័ត៌មានផ្ទុយពី CONTEXT។"
        )
        prev_text = (user_previous_context or "គ្មានព័ត៌មានមុន").strip()
        return (
            f"{grounding}\n\n"
            f"RAG CONTEXT (authoritative):\n{rag_context}\n\n"
            f"USER PREVIOUS CONTEXT:\n{prev_text}"
        )

    def _fallback_generic(self) -> str:
        return "អធ្យាស្រ័យខ្ញុំមិនអាចជួយបានទេ"

    def _fallback_no_context(self) -> str:
        return "អធ្យាស្រ័យខ្ញុំមិនអាចជួយបានទេ (រកមិនឃើញព័ត៌មានពាក់ព័ន្ធក្នុងឯកសារ)"

    def _fallback_generation_failed(self) -> str:
        return "អធ្យាស្រ័យខ្ញុំមិនអាចជួយបានទេ (ម៉ូដែលមិនបានឆ្លើយត្រឹមត្រូវ)"

    def _fallback_for(self, response_type: ResponseType, message: str) -> str:
        if response_type == ResponseType.KOMPLEX:
            return self._komplex_fallback_node(message)
        return message

    def _build_prompt(
        self,
        query: str,
        rag_context: str,
        response_type: ResponseType,
        previous_context: Optional[str],
    ) -> str:
        previous_context_payload = self._build_previous_context(
            rag_context=rag_context,
            user_previous_context=previous_context,
        )
        return general_pre_prompt(
            prompt=query,
            previous_context=previous_context_payload,
            response_type=response_type,
        )

    def _finalize_complex(self, raw_text: str) -> str:
        candidate_json = self._extract_candidate_json(raw_text)
        if not candidate_json:
            return self._fallback_for(
                ResponseType.KOMPLEX, self._fallback_generation_failed()
            )
        try:
            parsed = json.loads(candidate_json)
            if self._is_valid_topic_content(parsed):
                return json.dumps(parsed, ensure_ascii=False)
        except Exception:
            pass
        return self._fallback_for(
            ResponseType.KOMPLEX, self._fallback_generation_failed()
        )

    async def _generate_text(self, prompt: str) -> str:
        response = await asyncio.to_thread(
            client.models.generate_content,
            model="gemini-2.5-flash",
            contents=[prompt],
        )
        return (response.text or "").strip()

    async def ask_async(
        self,
        query: str,
        response_type: ResponseType,
        previous_context: Optional[str] = None,
        debug: bool = False,
    ):
        debug_info = {
            "retrieved_count": 0,
            "context_chars": 0,
            "sources": [],
            "generated": False,
            "response_type": response_type.value,
            "normal_json_guard_triggered": False,
            "normal_json_guard_attempted": False,
        }

        retrieved_docs = await self.hybrid_retrieve_async(query)
        debug_info["retrieved_count"] = len(retrieved_docs)
        logger.info(
            "[RAG/ASK] queryPreview=%r retrieved=%d",
            query[:120],
            len(retrieved_docs),
        )

        if not retrieved_docs:
            return (
                self._fallback_for(response_type, self._fallback_no_context()),
                [],
                debug_info,
            )

        context_text = self._build_rag_context(retrieved_docs)
        debug_info["context_chars"] = len(context_text)
        debug_info["sources"] = [
            (d.metadata.get("source") if hasattr(d, "metadata") else None)
            for d in retrieved_docs[:3]
        ]

        if not context_text.strip():
            return (
                self._fallback_for(response_type, self._fallback_no_context()),
                retrieved_docs,
                debug_info,
            )

        prompt = self._build_prompt(
            query=query,
            rag_context=context_text,
            response_type=response_type,
            previous_context=previous_context,
        )

        try:
            raw_answer = await self._generate_text(prompt)
        except Exception:
            logger.exception("[RAG/ASK] Gemini generate_content failed")
            raw_answer = ""

        if not raw_answer:
            return (
                self._fallback_for(
                    response_type,
                    self._fallback_generation_failed(),
                ),
                retrieved_docs,
                debug_info,
            )

        debug_info["generated"] = True

        if response_type == ResponseType.KOMPLEX:
            formatted = self._finalize_complex(raw_answer)
            return formatted, retrieved_docs, debug_info

        # responseType=NORMAL: guard against accidental JSON/code-fenced output.
        if self._looks_like_json_artifact(raw_answer):
            debug_info["normal_json_guard_triggered"] = True
            logger.warning(
                "[RAG/NORMAL-GUARD] JSON-like output detected. Reprompting markdown-only."
            )
            debug_info["normal_json_guard_attempted"] = True

            guarded_prompt = (
                prompt
                + "\n\nIMPORTANT: Your previous output appears to be JSON or a code-fenced block. "
                "Output Markdown ONLY. Do not output JSON/TopicContent_V3 and do not wrap anything in ``` fences. "
                "Start directly with your Markdown answer."
            )
            try:
                guarded_answer = await self._generate_text(guarded_prompt)
            except Exception:
                logger.exception(
                    "[RAG/NORMAL-GUARD] Gemini reprompt for markdown-only failed"
                )
                guarded_answer = ""

            if guarded_answer and not self._looks_like_json_artifact(guarded_answer):
                return guarded_answer, retrieved_docs, debug_info

            return self._fallback_generation_failed(), retrieved_docs, debug_info

        return raw_answer, retrieved_docs, debug_info