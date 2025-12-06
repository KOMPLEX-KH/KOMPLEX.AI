"""
RAG (Retrieval-Augmented Generation) Service
Handles document loading, vector store creation, and retrieval
"""
from pathlib import Path
from typing import List
from langchain_community.document_loaders import TextLoader
from langchain_community.vectorstores import Chroma
from langchain_community.embeddings import HuggingFaceEmbeddings
try:
    from langchain_text_splitters import RecursiveCharacterTextSplitter
except ImportError:
    # Fallback for older langchain versions
    from langchain.text_splitter import RecursiveCharacterTextSplitter
try:
    from langchain_core.documents import Document
except ImportError:
    from langchain.schema import Document


class RAGService:
    """Service for RAG operations: document loading, embedding, and retrieval"""
    
    def __init__(self, persist_directory: str = "./chroma_db"):
        """
        Initialize RAG service
        
        Args:
            persist_directory: Directory to persist ChromaDB vector store
        """
        self.persist_directory = persist_directory
        self.embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
        )
        self.vector_store = None
    
    def load_documents(self, file_path: str) -> List[Document]:
        """
        Load documents from a text file
        
        Args:
            file_path: Path to the document file
            
        Returns:
            List of Document objects
        """
        loader = TextLoader(file_path, encoding="utf-8")
        return loader.load()
    
    def load_documents_from_folder(self, folder_path: str, file_pattern: str = "*.txt") -> List[Document]:
        """
        Load all documents from a folder
        
        Args:
            folder_path: Path to the folder containing documents
            file_pattern: File pattern to match (default: "*.txt")
            
        Returns:
            List of Document objects from all matching files
        """
        folder = Path(folder_path)
        if not folder.exists():
            raise ValueError(f"Folder not found: {folder_path}")
        
        all_documents = []
        for file_path in folder.glob(file_pattern):
            try:
                docs = self.load_documents(str(file_path))
                all_documents.extend(docs)
            except Exception as e:
                print(f"Warning: Could not load {file_path}: {e}")
        
        return all_documents
    
    def create_vector_store(self, documents: List[Document], collection_name: str = "biology"):
        """
        Create or load vector store from documents
        
        Args:
            documents: List of Document objects to embed
            collection_name: Name of the ChromaDB collection
        """
        # Split documents into chunks
        chunks = self.text_splitter.split_documents(documents)
        
        # Create or load vector store
        self.vector_store = Chroma.from_documents(
            documents=chunks,
            embedding=self.embeddings,
            persist_directory=self.persist_directory,
            collection_name=collection_name
        )
        
        return self.vector_store
    
    def load_existing_vector_store(self, collection_name: str = "biology"):
        """
        Load an existing vector store
        
        Args:
            collection_name: Name of the ChromaDB collection
        """
        self.vector_store = Chroma(
            persist_directory=self.persist_directory,
            embedding_function=self.embeddings,
            collection_name=collection_name
        )
        return self.vector_store
    
    def retrieve_relevant_docs(self, query: str, k: int = 4) -> List[Document]:
        """
        Retrieve relevant documents for a query
        
        Args:
            query: Search query
            k: Number of documents to retrieve
            
        Returns:
            List of relevant Document objects
        """
        if self.vector_store is None:
            raise ValueError("Vector store not initialized. Call create_vector_store() or load_existing_vector_store() first.")
        
        return self.vector_store.similarity_search(query, k=k)
    
    def retrieve_with_scores(self, query: str, k: int = 4):
        """
        Retrieve relevant documents with similarity scores
        
        Args:
            query: Search query
            k: Number of documents to retrieve
            
        Returns:
            List of tuples (Document, score)
        """
        if self.vector_store is None:
            raise ValueError("Vector store not initialized. Call create_vector_store() or load_existing_vector_store() first.")
        
        return self.vector_store.similarity_search_with_score(query, k=k)
    
    def get_context_from_query(self, query: str, k: int = 4) -> str:
        """
        Get formatted context string from query for prompt injection
        
        Args:
            query: Search query
            k: Number of documents to retrieve
            
        Returns:
            Formatted context string
        """
        docs = self.retrieve_relevant_docs(query, k=k)
        context_parts = [doc.page_content for doc in docs]
        return "\n\n---\n\n".join(context_parts)


# Initialize RAG service instance (can be imported and reused)
def initialize_rag_service(
    docs_path: str = None, 
    docs_folder: str = "docs",
    collection_name: str = "biology",
    load_all_from_folder: bool = False
) -> RAGService:
    """
    Initialize and set up RAG service
    
    Args:
        docs_path: Path to a single document file (relative to src/ or absolute)
        docs_folder: Path to folder containing documents (relative to src/ or absolute)
        collection_name: Name of the ChromaDB collection
        load_all_from_folder: If True and docs_folder is provided, load all .txt files from folder
        
    Returns:
        Initialized RAGService instance
    """
    script_dir = Path(__file__).parent
    rag_service = RAGService(persist_directory=str(script_dir / "chroma_db"))
    
    # Try to load existing vector store first
    try:
        rag_service.load_existing_vector_store(collection_name=collection_name)
        return rag_service
    except Exception:
        pass  # Continue to create new vector store
    
    # Load documents based on provided parameters
    documents = []
    
    if load_all_from_folder and docs_folder:
        # Load all documents from folder
        folder_path = script_dir / docs_folder if not Path(docs_folder).is_absolute() else Path(docs_folder)
        documents = rag_service.load_documents_from_folder(str(folder_path))
    elif docs_folder:
        # Load specific folder (defaults to loading all .txt files)
        folder_path = script_dir / docs_folder if not Path(docs_folder).is_absolute() else Path(docs_folder)
        documents = rag_service.load_documents_from_folder(str(folder_path))
    elif docs_path:
        # Load single document file
        file_path = script_dir / docs_path if not Path(docs_path).is_absolute() else Path(docs_path)
        documents = rag_service.load_documents(str(file_path))
    else:
        # Default: try to load from docs/biology.txt
        default_path = script_dir / "docs" / "biology.txt"
        if default_path.exists():
            documents = rag_service.load_documents(str(default_path))
        else:
            # Try loading all files from docs folder
            docs_folder_path = script_dir / "docs"
            if docs_folder_path.exists():
                documents = rag_service.load_documents_from_folder(str(docs_folder_path))
    
    if documents:
        rag_service.create_vector_store(documents, collection_name=collection_name)
    else:
        raise ValueError("No documents found to create vector store. Please provide docs_path or docs_folder.")
    
    return rag_service

