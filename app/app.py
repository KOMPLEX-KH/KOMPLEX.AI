import logging
from pathlib import Path
from fastapi import FastAPI
from app.rag.rag_service import RAGService
from app.routes import ai_router, rag_router

app = FastAPI()

app.include_router(ai_router)
app.include_router(rag_router)


@app.on_event("startup")
async def startup_event():
    app.state.rag_service = RAGService()
    await app.state.rag_service.init_redis()

    DOCS_FOLDER = Path(__file__).parent / "docs"
    if DOCS_FOLDER.exists():
        app.state.rag_service.load_documents_from_folder(str(DOCS_FOLDER))
        app.state.rag_service.create_vector_store()
        logging.info("RAG service ready with documents.")
    else:
        logging.warning("Docs folder not found; RAG service ready without documents.")
